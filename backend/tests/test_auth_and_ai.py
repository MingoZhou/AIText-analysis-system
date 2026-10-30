import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from database import Base, get_db
from main import app
from models import Article, Keyword
from services.ai_service import (
    AIProviderError,
    _needs_article_context,
    _retrieval_terms,
    chat_completion,
)
from services.auth_service import hash_password, verify_password


class PasswordTests(unittest.TestCase):
    def test_passwords_use_salted_pbkdf2(self):
        first = hash_password("zhou1999")
        second = hash_password("zhou1999")
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("pbkdf2_sha256$"))
        self.assertTrue(verify_password("zhou1999", first))
        self.assertFalse(verify_password("wrong-password", first))


class AIProviderErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_nvidia_529_retries_and_preserves_provider_message(self):
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                529,
                json={"error": {"message": "capacity temporarily exhausted"}},
                request=request,
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch("services.ai_service.httpx.AsyncClient", return_value=client), patch(
            "services.ai_service.asyncio.sleep", new=AsyncMock()
        ):
            with self.assertRaises(AIProviderError) as raised:
                await chat_completion(
                    "https://integrate.api.nvidia.com/v1",
                    "key",
                    "model-id",
                    [{"role": "user", "content": "test"}],
                    provider_key="nvidia",
                )
        self.assertEqual(calls, 4)
        self.assertEqual(raised.exception.status_code, 529)
        self.assertEqual(raised.exception.attempts, 4)
        self.assertIn("capacity temporarily exhausted", str(raised.exception))

    async def test_moonshot_400_is_not_retried_and_omits_sampling_options(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                400,
                json={"error": {"message": "invalid model: old-model"}},
                request=request,
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch("services.ai_service.httpx.AsyncClient", return_value=client):
            with self.assertRaises(AIProviderError) as raised:
                await chat_completion(
                    "https://api.moonshot.cn/v1",
                    "key",
                    "old-model",
                    [{"role": "user", "content": "test"}],
                    provider_key="moonshot",
                )
        self.assertEqual(len(requests), 1)
        payload = json.loads(requests[0].content)
        self.assertNotIn("temperature", payload)
        self.assertNotIn("max_tokens", payload)
        self.assertIn("invalid model: old-model", str(raised.exception))


class AIContextSelectionTests(unittest.TestCase):
    def test_general_questions_skip_document_context(self):
        self.assertFalse(_needs_article_context("你好，你是什么模型？"))
        self.assertFalse(_needs_article_context("测试一下"))
        self.assertTrue(_needs_article_context("高质量数据集应当如何构建？"))
        self.assertTrue(_needs_article_context("你好，请分析高质量数据集建设路径"))

    def test_domain_question_produces_retrieval_terms(self):
        terms = _retrieval_terms("低压压铸铝合金轮毂缩松缺陷如何预测")
        self.assertIn("压铸", terms)
        self.assertIn("轮毂", terms)
        self.assertNotIn("如何", terms)


class AuthenticationIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async def override_get_db():
            async with self.session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.engine.dispose()
        self.temp_dir.cleanup()

    async def _register(self, username: str) -> tuple[str, dict]:
        response = await self.client.post(
            "/api/auth/register",
            json={"username": username, "password": "password123", "display_name": username},
        )
        self.assertEqual(response.status_code, 201, response.text)
        data = response.json()
        return data["access_token"], data["user"]

    @staticmethod
    def _headers(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    async def test_login_and_cross_user_data_isolation(self):
        unauthorized = await self.client.get("/api/keywords")
        self.assertEqual(unauthorized.status_code, 401)

        admin_token, admin = await self._register("admin")
        admin_keyword = await self.client.post(
            "/api/keywords",
            headers=self._headers(admin_token),
            json={"keyword": "高质量数据集"},
        )
        self.assertEqual(admin_keyword.status_code, 200, admin_keyword.text)
        keyword_id = admin_keyword.json()["id"]

        async with self.session_factory() as db:
            db.add(Article(
                user_id=admin["id"],
                keyword_id=keyword_id,
                title="管理员文献",
                content="仅管理员可见",
            ))
            await db.commit()
            article_id = (await db.execute(select(Article.id))).scalar_one()

        other_token, _ = await self._register("other-user")
        other_headers = self._headers(other_token)
        other_keywords = await self.client.get("/api/keywords", headers=other_headers)
        self.assertEqual(other_keywords.json(), [])
        hidden_article = await self.client.get(
            f"/api/articles/{article_id}", headers=other_headers
        )
        self.assertEqual(hidden_article.status_code, 404)
        hidden_update = await self.client.put(
            f"/api/keywords/{keyword_id}",
            headers=other_headers,
            json={"keyword": "越权修改"},
        )
        self.assertEqual(hidden_update.status_code, 404)

        order = ["moonshot", "nvidia", "ollama"]
        saved = await self.client.put(
            "/api/providers/preset-order", headers=other_headers, json={"keys": order}
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        admin_order = await self.client.get(
            "/api/providers/preset-order", headers=self._headers(admin_token)
        )
        self.assertNotEqual(admin_order.json()["keys"][:3], order)

        bad_login = await self.client.post(
            "/api/auth/login", json={"username": "admin", "password": "bad"}
        )
        self.assertEqual(bad_login.status_code, 401)


if __name__ == "__main__":
    unittest.main()

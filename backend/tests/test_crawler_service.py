import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from pypdf import PdfWriter
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from database import Base, async_session
from models import CrawlLog, DataSource, Keyword, User
from services.crawler_service import (
    DiscoveryBatch,
    _archive_first_pdf_attachment,
    _discover_bing,
    _discover_site_search,
    _extract_html,
    _get_robots_checker,
    _relevance,
    build_query_plan,
    canonicalize_url,
    crawl_keyword,
)


class CrawlerUtilityTests(unittest.TestCase):
    def test_canonicalize_url_removes_tracking_and_fragment(self):
        value = canonicalize_url(
            "https://Example.COM/a//b/?utm_source=test&b=2&a=1#section"
        )
        self.assertEqual(value, "https://example.com/a/b?a=1&b=2")

    def test_relevance_uses_aliases_and_exclusions(self):
        keyword = Keyword(
            user_id=1,
            keyword="设计制造一体化",
            aliases=["设计工艺协同"],
            exact_phrases=[],
            excluded_terms=["招聘"],
        )
        score, matched = _relevance(
            keyword,
            "设计工艺协同平台建设方案",
            "面向制造企业的设计与工艺协同。",
            "",
        )
        self.assertGreater(score, 0)
        self.assertIn("设计工艺协同", matched)

        excluded_score, _ = _relevance(
            keyword,
            "设计工艺协同工程师招聘",
            "",
            "",
        )
        self.assertLess(excluded_score, 0)

    def test_extract_html_prefers_article_and_collects_attachments(self):
        html = """
        <html><head>
          <meta property="og:title" content="行业高质量数据集建设方案">
          <meta name="publishdate" content="2026年08月04日">
          <meta name="source" content="测试部门">
        </head><body>
          <nav>导航噪声</nav>
          <article>
            <p>这是用于验证正文提取的第一段政策内容，长度足够进入正文。</p>
            <p>这是用于验证正文提取的第二段政策内容，并包含更多有效信息。</p>
            <a href="/files/report.pdf">附件下载</a>
          </article>
        </body></html>
        """
        response = httpx.Response(
            200,
            text=html,
            headers={"content-type": "text/html; charset=utf-8"},
            request=httpx.Request("GET", "https://example.gov.cn/policy/1"),
        )
        parsed = _extract_html(response, {"title": "", "snippet": ""})
        self.assertEqual(parsed["title"], "行业高质量数据集建设方案")
        self.assertEqual(parsed["publish_date"], "2026-08-04")
        self.assertIn("第一段政策内容", parsed["content"])
        self.assertEqual(parsed["attachments"][0]["url"], "https://example.gov.cn/files/report.pdf")


class QueryPlanTests(unittest.IsolatedAsyncioTestCase):
    async def test_query_plan_contains_authoritative_site_scope(self):
        keyword = Keyword(
            user_id=1,
            keyword="高质量数据集",
            aliases=["行业数据集"],
            exact_phrases=[],
            excluded_terms=["招聘"],
            site_filters=[],
            source_ids=[],
        )
        async with async_session() as db:
            plan = await build_query_plan(keyword, db)
        self.assertTrue(any(item["source_kind"] == "official" for item in plan))
        self.assertTrue(any(
            item.get("discovery_provider") == "official_site"
            and item.get("required_domain") == "gov.cn"
            for item in plan
        ))
        self.assertTrue(any('"行业数据集"' in item["query"] for item in plan))

    async def test_pdf_attachment_is_archived_without_replacing_parent_url(self):
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        payload = io.BytesIO()
        writer.write(payload)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=payload.getvalue(),
                headers={"content-type": "application/pdf"},
                request=request,
            )

        attachments = [{"title": "建设指南", "url": "https://example.gov.cn/files/guide.pdf"}]
        with tempfile.TemporaryDirectory() as temp_dir:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with patch("services.crawler_service.PDF_DIR", Path(temp_dir)):
                    archived = await _archive_first_pdf_attachment(
                        client, attachments, "政策页面", 1
                    )
            self.assertIsNotNone(archived)
            self.assertTrue(Path(archived["file_path"]).exists())
            self.assertEqual(attachments[0]["archive_status"], "saved")


class DiscoveryPolicyTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _source(domain: str, source_id: int = 1):
        return SimpleNamespace(
            id=source_id,
            name=domain,
            source_kind="official",
            base_url=f"https://www.{domain}",
            domain=domain,
            config={},
        )

    @staticmethod
    def _plan(domain: str, term: str = "设计制造工艺一体化"):
        return {
            "source_id": 1,
            "source_name": domain,
            "source_kind": "official",
            "query": f'site:{domain} "{term}"',
            "required_domain": domain,
            "term": term,
            "limit": 4,
        }

    async def test_miit_uses_native_json_api_without_bing(self):
        payload = {
            "success": True,
            "data": {
                "searchResult": {
                    "dataResults": [
                        {
                            "data": {
                                "title": "工业母机高质量标准体系建设方案",
                                "url": "/xwfb/test.html",
                                "cdate": "1757520000000",
                                "jsearch_date": "2025-09-11",
                            }
                        }
                    ]
                }
            },
        }

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.host, "www.miit.gov.cn")
            self.assertEqual(request.url.params["q"], "设计制造工艺一体化")
            return httpx.Response(200, json=payload, request=request)

        keyword = SimpleNamespace(keyword="设计制造工艺一体化")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with (
                patch("services.crawler_service.CRAWLER_RESPECT_ROBOTS_TXT", False),
                patch(
                    "services.crawler_service._discover_bing",
                    new_callable=AsyncMock,
                ) as bing,
            ):
                batch = await _discover_site_search(
                    client,
                    self._plan("miit.gov.cn"),
                    self._source("miit.gov.cn"),
                    keyword,
                )

        self.assertEqual(batch.status, "success")
        self.assertEqual(batch.provider, "official:miit.gov.cn")
        self.assertEqual(len(batch.items), 1)
        self.assertEqual(batch.items[0]["publish_date"], "2025-09-11")
        self.assertEqual(
            batch.items[0]["url"],
            "https://www.miit.gov.cn/xwfb/test.html",
        )
        bing.assert_not_awaited()

    async def test_official_source_without_adapter_never_falls_back_to_bing(self):
        keyword = SimpleNamespace(keyword="设计制造工艺一体化")
        async with httpx.AsyncClient() as client:
            with patch(
                "services.crawler_service._discover_bing",
                new_callable=AsyncMock,
            ) as bing:
                batch = await _discover_site_search(
                    client,
                    self._plan("sasac.gov.cn"),
                    self._source("sasac.gov.cn"),
                    keyword,
                )

        self.assertEqual(batch.status, "unsupported")
        self.assertIn("禁止隐式回退到 Bing", batch.error)
        bing.assert_not_awaited()

    async def test_nda_uses_public_two_stage_search_api(self):
        request_commands = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8"))
            request_commands.append(payload["cmd"])
            if payload["cmd"] == "open_pit":
                data = {
                    "data": {
                        "task_d3trpiyv8d5": {
                            "master": [{"data": {"id": "pit-test"}}]
                        }
                    }
                }
            else:
                self.assertEqual(payload["params"]["pit_id"], "pit-test")
                self.assertEqual(payload["params"]["query"], "高质量数据集")
                data = {
                    "data": {
                        "task_d3trpiyv8d5": {
                            "master": [{
                                "data": {
                                    "docs": [{
                                        "title": "高质量数据集建设指引",
                                        "url": "/sjj/policy/guide_pc.html",
                                        "time": "2025-08-30 12:00:00",
                                        "content": "公开政策内容",
                                    }]
                                }
                            }]
                        }
                    }
                }
            return httpx.Response(200, json=data, request=request)

        keyword = SimpleNamespace(keyword="高质量数据集")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with (
                patch("services.crawler_service.CRAWLER_RESPECT_ROBOTS_TXT", False),
                patch("services.crawler_service.CRAWLER_REQUEST_INTERVAL", 0),
                patch(
                    "services.crawler_service._discover_bing",
                    new_callable=AsyncMock,
                ) as bing,
            ):
                batch = await _discover_site_search(
                    client,
                    self._plan("nda.gov.cn", "高质量数据集"),
                    self._source("nda.gov.cn", 2),
                    keyword,
                )

        self.assertEqual(request_commands, ["open_pit", "search_global"])
        self.assertEqual(batch.status, "success")
        self.assertEqual(batch.provider, "official:nda.gov.cn")
        self.assertEqual(batch.items[0]["publish_date"], "2025-08-30")
        self.assertEqual(
            batch.items[0]["url"],
            "https://www.nda.gov.cn/sjj/policy/guide_pc.html",
        )
        bing.assert_not_awaited()

    async def test_empty_native_result_is_not_retried_through_bing(self):
        payload = {"success": True, "data": {"searchResult": {"dataResults": []}}}

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload, request=request)

        keyword = SimpleNamespace(keyword="没有结果的测试词")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with (
                patch("services.crawler_service.CRAWLER_RESPECT_ROBOTS_TXT", False),
                patch(
                    "services.crawler_service._discover_bing",
                    new_callable=AsyncMock,
                ) as bing,
            ):
                batch = await _discover_site_search(
                    client,
                    self._plan("miit.gov.cn", "没有结果的测试词"),
                    self._source("miit.gov.cn"),
                    keyword,
                )

        self.assertEqual(batch.status, "success")
        self.assertEqual(batch.items, [])
        bing.assert_not_awaited()

    async def test_bing_verification_opens_circuit_breaker(self):
        import services.crawler_service as crawler_service

        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            return httpx.Response(
                200,
                text="<html><title>验证</title><body>验证您是真人</body></html>",
                request=request,
            )

        source = SimpleNamespace(id=8, name="Bing", source_kind="search")
        plan = {
            "query": '"高质量数据集"',
            "limit": 5,
            "source_kind": "search",
        }
        old_until = crawler_service._bing_cooldown_until
        old_reason = crawler_service._bing_cooldown_reason
        crawler_service._bing_cooldown_until = 0
        crawler_service._bing_cooldown_reason = ""
        try:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                first = await _discover_bing(client, plan, source)
                second = await _discover_bing(client, plan, source)
        finally:
            crawler_service._bing_cooldown_until = old_until
            crawler_service._bing_cooldown_reason = old_reason

        self.assertEqual(first.status, "blocked")
        self.assertTrue(first.stop_provider)
        self.assertEqual(second.status, "blocked")
        self.assertEqual(request_count, 1)

    async def test_robots_lookup_failure_is_fail_closed(self):
        import services.crawler_service as crawler_service

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="unavailable", request=request)

        crawler_service._robots_cache.clear()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            checker = await _get_robots_checker(client, "https://policy.example/a")

        self.assertFalse(checker.is_allowed("https://policy.example/a"))


class CrawlRollbackRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with self.session_factory() as db:
            user = User(username="crawler-test", password_hash="test")
            db.add(user)
            await db.flush()
            source = DataSource(
                user_id=user.id,
                name="测试权威来源",
                source_kind="official",
                base_url="https://example.com",
                domain="example.com",
                priority=1,
                config={},
            )
            db.add(source)
            await db.flush()
            keyword = Keyword(
                user_id=user.id,
                keyword="高质量数据集",
                source_ids=[source.id],
                notify_on_crawl=False,
            )
            db.add(keyword)
            await db.flush()
            log = CrawlLog(
                user_id=user.id,
                keyword_id=keyword.id,
                keyword_text=keyword.keyword,
                source_ids=[source.id],
            )
            db.add(log)
            await db.commit()
            self.user_id = user.id
            self.source_id = source.id
            self.keyword_id = keyword.id
            self.log_id = log.id

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_item_rollback_does_not_expire_log_id_in_main_loop(self):
        batch = DiscoveryBatch(
            items=[{
                "title": "测试条目",
                "url": "https://example.com/test",
                "snippet": "高质量数据集",
                "matched_query": '"高质量数据集"',
            }],
            provider="official:example.com",
        )

        async def process_with_rollback(_client, db, *_args):
            await db.rollback()
            current = await db.get(CrawlLog, self.log_id)
            current.saved_count += 1
            current.failed_count += 1
            await db.commit()

        async with self.session_factory() as db:
            with (
                patch("services.crawler_service._discover", new=AsyncMock(return_value=batch)),
                patch("services.crawler_service._process_item", new=process_with_rollback),
            ):
                result = await crawl_keyword(
                    self.keyword_id,
                    db,
                    self.log_id,
                    [self.source_id],
                    user_id=self.user_id,
                )

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["found"], 1)
        self.assertEqual(result["saved"], 1)
        self.assertEqual(result["failed"], 1)


if __name__ == "__main__":
    unittest.main()

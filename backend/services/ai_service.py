"""Provider-aware OpenAI-compatible AI client and analysis functions."""
import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import AIProvider, Article, ArticleKeyword

REQUEST_TIMEOUT = 120
RETRY_DELAYS = (1, 2, 4)
RETRY_STATUS_CODES = {429, 500, 502, 503, 504, 529}


def _build_headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _provider_key(base_url: str, explicit: str = "") -> str:
    if explicit and explicit != "custom":
        return explicit.lower()
    host = base_url.lower()
    mappings = {
        "nvidia.com": "nvidia",
        "moonshot.cn": "moonshot",
        "deepseek.com": "deepseek",
        "openai.com": "openai",
        "11434": "ollama",
    }
    return next((key for marker, key in mappings.items() if marker in host), explicit or "custom")


def _extract_error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, dict):
                message = error.get("message") or error.get("detail") or error.get("code")
                if message:
                    return str(message)
            elif error:
                return str(error)
            for key in ("message", "detail", "msg"):
                if data.get(key):
                    return str(data[key])
    except (ValueError, TypeError):
        pass
    text = response.text.strip()
    return text[:1000] if text else "上游服务未返回错误详情"


@dataclass
class AIProviderError(Exception):
    status_code: int | None
    provider_key: str
    model: str
    provider_message: str
    retryable: bool = False
    attempts: int = 1

    @property
    def suggestion(self) -> str:
        if self.status_code == 529:
            return "NVIDIA 推理服务当前容量不足，请稍后重试或暂时切换备用模型。"
        if self.status_code == 429:
            return "请求频率或额度已达上限，请稍后重试并检查账户额度。"
        if self.status_code == 400:
            return "请刷新模型列表，确认模型名称有效；若仍失败，请缩短分析内容并检查模型参数限制。"
        if self.status_code in {401, 403}:
            return "请检查 API Key 是否正确、有效并具有该模型权限。"
        if self.retryable:
            return "上游服务暂时不可用，请稍后重试或切换备用提供商。"
        return "请检查 Base URL、模型名称和提供商配置。"

    def __str__(self) -> str:
        provider = self.provider_key.upper() if self.provider_key else "AI 提供商"
        status = f"HTTP {self.status_code}" if self.status_code else "网络错误"
        retry_text = f"，已自动尝试 {self.attempts} 次" if self.attempts > 1 else ""
        return (
            f"{provider} 调用失败（{status}{retry_text}）：{self.provider_message}。"
            f"{self.suggestion}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "status_code": self.status_code,
            "provider": self.provider_key,
            "model": self.model,
            "provider_message": self.provider_message,
            "retryable": self.retryable,
            "attempts": self.attempts,
            "suggestion": self.suggestion,
        }


def _retry_delay(response: httpx.Response, retry_index: int) -> float:
    retry_after = response.headers.get("Retry-After", "").strip()
    try:
        return min(30.0, max(0.0, float(retry_after)))
    except ValueError:
        return float(RETRY_DELAYS[retry_index])


async def _request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    provider_key: str,
    model: str = "",
    payload: dict | None = None,
    timeout: int = REQUEST_TIMEOUT,
) -> dict:
    attempts = len(RETRY_DELAYS) + 1
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        for attempt in range(attempts):
            try:
                response = await client.request(method, url, json=payload)
            except httpx.RequestError as exc:
                if attempt < len(RETRY_DELAYS):
                    await asyncio.sleep(RETRY_DELAYS[attempt])
                    continue
                raise AIProviderError(
                    None,
                    provider_key,
                    model,
                    str(exc) or "无法连接到上游服务",
                    retryable=True,
                    attempts=attempt + 1,
                ) from exc

            if 200 <= response.status_code < 300:
                try:
                    return response.json()
                except ValueError as exc:
                    raise AIProviderError(
                        response.status_code,
                        provider_key,
                        model,
                        "上游成功响应不是有效 JSON",
                    ) from exc

            retryable = response.status_code in RETRY_STATUS_CODES
            if retryable and attempt < len(RETRY_DELAYS):
                await asyncio.sleep(_retry_delay(response, attempt))
                continue
            raise AIProviderError(
                response.status_code,
                provider_key,
                model,
                _extract_error_message(response),
                retryable=retryable,
                attempts=attempt + 1,
            )
    raise RuntimeError("unreachable")


async def get_models(base_url: str, api_key: str) -> list[str]:
    """Return model IDs or raise an actionable provider error."""
    provider_key = _provider_key(base_url)
    data = await _request_json(
        "GET",
        f"{base_url.rstrip('/')}/models",
        headers=_build_headers(api_key),
        provider_key=provider_key,
        timeout=30,
    )
    models = data.get("data", [])
    return sorted({str(item.get("id")) for item in models if isinstance(item, dict) and item.get("id")})


async def test_connection(base_url: str, api_key: str) -> dict:
    try:
        models = await get_models(base_url, api_key)
        return {
            "success": True,
            "message": f"连接成功，发现 {len(models)} 个模型",
            "model_count": len(models),
        }
    except AIProviderError as exc:
        return {"success": False, "message": str(exc), "error": exc.as_dict()}


def _chat_payload(
    provider_key: str,
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    context_window: int,
) -> dict:
    if not model.strip():
        raise AIProviderError(
            400,
            provider_key,
            model,
            "尚未选择默认模型",
        )
    payload: dict[str, Any] = {"model": model.strip(), "messages": messages}
    token_limit = max(256, max_tokens)
    if context_window > 0:
        token_limit = min(token_limit, max(256, context_window // 4))

    # Moonshot model families impose different sampling constraints. Omitting
    # optional sampling fields lets the selected model apply its valid defaults.
    if provider_key != "moonshot":
        payload["temperature"] = temperature
        payload["max_tokens"] = token_limit
    return payload


async def chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    provider_key: str = "custom",
    context_window: int = 0,
) -> str:
    provider_key = _provider_key(base_url, provider_key)
    payload = _chat_payload(
        provider_key, model, messages, temperature, max_tokens, context_window
    )
    data = await _request_json(
        "POST",
        f"{base_url.rstrip('/')}/chat/completions",
        headers=_build_headers(api_key),
        provider_key=provider_key,
        model=model,
        payload=payload,
    )
    try:
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(
                str(item.get("text", "")) for item in content if isinstance(item, dict)
            )
        if not isinstance(content, str) or not content.strip():
            raise KeyError("empty content")
        return content
    except (KeyError, IndexError, TypeError) as exc:
        raise AIProviderError(
            200,
            provider_key,
            model,
            "响应中缺少 choices[0].message.content",
        ) from exc


async def get_current_provider(db: AsyncSession, user_id: int) -> AIProvider | None:
    # 先尝试管理员路径：查询用户自己配置且标记为当前的 Provider
    result = await db.execute(
        select(AIProvider).where(
            AIProvider.user_id == user_id,
            AIProvider.is_current == True,
            AIProvider.is_active == True,
        )
    )
    provider = result.scalars().first()
    if provider:
        return provider

    # 普通用户路径：通过 ProviderPreference.current_provider_id 获取
    from models import ProviderPreference
    from services.permission_service import get_user_accessible_provider_ids, is_admin
    from models import User

    user = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
    if user and not is_admin(user):
        pref = await db.get(ProviderPreference, user_id)
        if pref and pref.current_provider_id:
            accessible = await get_user_accessible_provider_ids(db, user)
            if pref.current_provider_id in accessible:
                prov_result = await db.execute(
                    select(AIProvider).where(
                        AIProvider.id == pref.current_provider_id,
                        AIProvider.is_active == True,
                    )
                )
                return prov_result.scalars().first()

    return None


def _context_limit(provider: AIProvider) -> int:
    if provider.context_window > 0:
        return min(48_000, max(8_000, int(provider.context_window * 1.5) - 6_000))
    return 18_000


_RETRIEVAL_STOP_TERMS = {
    "一个", "一下", "什么", "为何", "为什么", "如何", "怎么", "可以",
    "请问", "这个", "这些", "那些", "进行", "相关", "文章", "内容", "分析",
    "基于", "帮我", "以及", "是否", "目前", "当前", "我们", "你们",
}


def _retrieval_terms(text: str) -> list[str]:
    """Build compact Chinese/Latin search terms without another model call."""
    normalized = re.sub(r"\s+", "", (text or "").casefold())
    terms: list[str] = []
    for segment in re.findall(r"[\u4e00-\u9fff]+|[a-z0-9][a-z0-9_.-]+", normalized):
        candidates = [segment]
        if "\u4e00" <= segment[0] <= "\u9fff" and len(segment) > 6:
            candidates = [
                segment[index:index + size]
                for size in (2, 3, 4)
                for index in range(len(segment) - size + 1)
            ]
        for candidate in candidates:
            if candidate in _RETRIEVAL_STOP_TERMS or len(candidate) < 2:
                continue
            if candidate not in terms:
                terms.append(candidate)
    return terms[:40]


def _article_query_score(article: Article, base_score: float, terms: list[str]) -> float:
    if not terms:
        return base_score
    title = (article.title or "").casefold()
    content = (article.content or article.summary or "")[:12_000].casefold()
    return base_score + sum(
        (8 if term in title else 0) + (1 if term in content else 0)
        for term in terms
    )


def _best_excerpt(text: str, terms: list[str], limit: int) -> str:
    if len(text) <= limit or not terms:
        return text[:limit]
    folded = text.casefold()
    positions = [folded.find(term) for term in terms]
    positions = [position for position in positions if position >= 0]
    if not positions:
        return text[:limit]
    start = max(0, min(positions) - min(240, limit // 5))
    return text[start:start + limit]


def _needs_article_context(message: str) -> bool:
    """Greetings and model-identity questions do not need document retrieval."""
    compact = re.sub(r"[\s，。！？、,.!?：:；;]+", "", (message or "").casefold())
    if len(compact) > 36:
        return True
    if compact in {
        "你好", "您好", "hello", "hi", "在吗", "谢谢", "感谢", "测试一下", "测试",
    }:
        return False
    model_phrases = ("你是谁", "你是什么模型", "你用的什么模型", "当前是什么模型")
    return not (len(compact) <= 20 and any(phrase in compact for phrase in model_phrases))


async def _gather_context(
    db: AsyncSession,
    user_id: int,
    article_ids: list[int],
    keyword_id: int | None,
    max_chars: int,
    query_text: str = "",
) -> str:
    ranked_articles: list[tuple[Article, float]]
    if article_ids:
        articles = (
            await db.execute(
                select(Article)
                .where(Article.user_id == user_id, Article.id.in_(article_ids))
                .order_by(Article.crawl_date.desc())
            )
        ).scalars().all()
        ranked_articles = [(article, 0.0) for article in articles]
    elif keyword_id:
        rows = (
            await db.execute(
                select(Article, ArticleKeyword.relevance_score)
                .join(ArticleKeyword, ArticleKeyword.article_id == Article.id)
                .where(
                    Article.user_id == user_id,
                    ArticleKeyword.keyword_id == keyword_id,
                )
                .order_by(
                    ArticleKeyword.relevance_score.desc(),
                    Article.crawl_date.desc(),
                )
                .limit(30)
            )
        ).all()
        ranked_articles = [(article, float(score or 0)) for article, score in rows]
    else:
        ranked_articles = []

    terms = _retrieval_terms(query_text)
    ranked_articles.sort(
        key=lambda row: _article_query_score(row[0], row[1], terms), reverse=True
    )

    parts: list[str] = []
    used = 0
    for article, _ in ranked_articles:
        remaining = max_chars - used
        if remaining < 200:
            break
        header = f"【标题】{article.title}\n【来源】{article.source_name}\n【内容】"
        raw_body = article.content or article.summary or ""
        if not raw_body.strip():
            continue
        body = _best_excerpt(raw_body, terms, min(2400, remaining - len(header)))
        part = f"{header}{body}\n"
        parts.append(part)
        used += len(part) + 5
    return "\n---\n".join(parts)


def _provider_error(exc: AIProviderError) -> dict:
    return {"error": f"AI 调用失败：{exc}", "error_detail": exc.as_dict()}


def _parse_json_result(value: str) -> Any:
    text = value.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
    return json.loads(text.strip())


async def _analysis_context(
    db: AsyncSession, user_id: int, article_ids: list[int], keyword_id: int | None
) -> tuple[AIProvider | None, str]:
    provider = await get_current_provider(db, user_id)
    if not provider:
        return None, ""
    context = await _gather_context(
        db, user_id, article_ids, keyword_id, _context_limit(provider)
    )
    return provider, context


async def generate_summary(
    db: AsyncSession, user_id: int, article_ids: list[int], keyword_id: int | None, model: str | None
) -> dict:
    provider, context = await _analysis_context(db, user_id, article_ids, keyword_id)
    if not provider:
        return {"error": "未配置当前 AI 提供商，请先在 AI 分析页面配置"}
    if not context:
        return {"error": "未找到当前账号可分析的文章内容"}
    use_model = model or provider.default_model
    messages = [
        {"role": "system", "content": "你是一个专业的政策资讯分析助手。请对用户提供的文章内容进行深度总结分析。"},
        {"role": "user", "content": f"请对以下文章内容进行总结分析，输出格式包含：\n1. 核心要点（3-5条）\n2. 政策背景\n3. 影响分析\n4. 建议关注点\n\n文章内容：\n{context}"},
    ]
    try:
        text = await chat_completion(
            provider.base_url, provider.api_key, use_model, messages, 0.3, 4096,
            provider.provider_key, provider.context_window,
        )
        return {"summary": text, "model": use_model, "provider": provider.name, "provider_id": provider.id}
    except AIProviderError as exc:
        return _provider_error(exc)


async def generate_wordcloud(
    db: AsyncSession, user_id: int, article_ids: list[int], keyword_id: int | None, model: str | None
) -> dict:
    provider, context = await _analysis_context(db, user_id, article_ids, keyword_id)
    if not provider:
        return {"error": "未配置当前 AI 提供商"}
    if not context:
        return {"error": "未找到当前账号可分析的文章内容"}
    use_model = model or provider.default_model
    messages = [
        {"role": "system", "content": "你是一个关键词提取专家。请从文本中提取关键词并评估其重要性。"},
        {"role": "user", "content": f"请从以下文本中提取 30-50 个关键词，返回 JSON 数组，每项为 {{\"name\": \"关键词\", \"value\": 权重值(1-100)}}。只返回 JSON。\n\n文本：\n{context[:8000]}"},
    ]
    try:
        text = await chat_completion(
            provider.base_url, provider.api_key, use_model, messages, 0.2, 2048,
            provider.provider_key, provider.context_window,
        )
        return {"words": _parse_json_result(text), "model": use_model, "provider": provider.name, "provider_id": provider.id}
    except json.JSONDecodeError:
        return {"error": "AI 返回格式异常，请重试", "raw": text[:500]}
    except AIProviderError as exc:
        return _provider_error(exc)


async def generate_chart_analysis(
    db: AsyncSession, user_id: int, article_ids: list[int], keyword_id: int | None, model: str | None
) -> dict:
    provider, context = await _analysis_context(db, user_id, article_ids, keyword_id)
    if not provider:
        return {"error": "未配置当前 AI 提供商"}
    if not context:
        return {"error": "未找到当前账号可分析的文章内容"}
    use_model = model or provider.default_model
    prompt = f'''请分析以下文章内容，只返回 JSON：
{{
  "topic_distribution": [{{"name": "主题名", "value": 1}}],
  "sentiment": [{{"name": "正面", "value": 1}}, {{"name": "中性", "value": 1}}, {{"name": "负面", "value": 1}}],
  "keyword_frequency": [{{"name": "关键词", "value": 1}}],
  "source_distribution": [{{"name": "来源", "value": 1}}],
  "time_trend": [{{"date": "日期", "count": 1}}],
  "insights": ["洞察1", "洞察2", "洞察3"]
}}

文章内容：
{context[:8000]}'''
    messages = [
        {"role": "system", "content": "你是一个数据分析专家。请生成可直接可视化的结构化数据。"},
        {"role": "user", "content": prompt},
    ]
    try:
        text = await chat_completion(
            provider.base_url, provider.api_key, use_model, messages, 0.3, 4096,
            provider.provider_key, provider.context_window,
        )
        return {"charts": _parse_json_result(text), "model": use_model, "provider": provider.name, "provider_id": provider.id}
    except json.JSONDecodeError:
        return {"error": "AI 返回格式异常，请重试", "raw": text[:500]}
    except AIProviderError as exc:
        return _provider_error(exc)


async def chat_with_context(
    db: AsyncSession,
    user_id: int,
    message: str,
    article_ids: list[int],
    keyword_id: int | None,
    model: str | None,
) -> dict:
    provider = await get_current_provider(db, user_id)
    if not provider:
        return {"error": "未配置当前 AI 提供商"}
    use_model = model or provider.default_model
    context = ""
    if _needs_article_context(message):
        context = await _gather_context(
            db,
            user_id,
            article_ids,
            keyword_id,
            min(4_000, _context_limit(provider)),
            query_text=message,
        )
    system_prompt = (
        "你是一个专业的政策资讯分析助手。涉及资料的问题必须基于参考文章回答；"
        "寒暄、模型信息等一般问题直接简洁回答。"
        f"当前服务商为 {provider.name}，调用模型标识为 {use_model}。"
    )
    if context:
        system_prompt += f"\n\n参考文章：\n{context}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]
    try:
        started_at = time.perf_counter()
        text = await chat_completion(
            provider.base_url, provider.api_key, use_model, messages, 0.7, 2048,
            provider.provider_key, provider.context_window,
        )
        return {
            "reply": text,
            "model": use_model,
            "provider": provider.name,
            "provider_id": provider.id,
            "elapsed_ms": round((time.perf_counter() - started_at) * 1000),
            "context_chars": len(context),
        }
    except AIProviderError as exc:
        return _provider_error(exc)


# ========== 会话级智能对话（带记忆 + 上下文压缩）==========

# 触发上下文压缩的阈值（消息字符数）
COMPRESS_THRESHOLD = 12_000
# 压缩后保留的最近消息数
KEEP_RECENT_MESSAGES = 6


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数"""
    return len(text) // 4 if text else 0


async def compress_session_context(db: AsyncSession, session) -> str:
    """将会话历史消息压缩为记忆摘要"""
    provider = await get_current_provider(db, session.user_id)
    if not provider:
        return ""

    # 拼接历史消息
    history_parts = []
    if session.memory_summary:
        history_parts.append(f"【之前的对话摘要】\n{session.memory_summary}")

    for msg in session.messages:
        if msg.role == "system":
            continue
        label = "用户" if msg.role == "user" else "助手"
        history_parts.append(f"{label}: {msg.content}")

    if len(history_parts) <= 1:
        return session.memory_summary

    full_history = "\n\n".join(history_parts)

    use_model = session.model or provider.default_model
    messages = [
        {
            "role": "system",
            "content": "你是一个对话记忆管理专家。请将以下对话历史压缩为简洁的记忆摘要，保留关键信息、用户意图、已讨论的结论和待跟进事项。摘要应简洁且信息密度高。",
        },
        {"role": "user", "content": f"请压缩以下对话历史为记忆摘要（不超过500字）：\n\n{full_history[:8000]}"},
    ]

    try:
        summary = await chat_completion(
            provider.base_url, provider.api_key, use_model, messages, 0.3, 1024,
            provider.provider_key, provider.context_window,
        )
        return summary
    except AIProviderError:
        return session.memory_summary


async def chat_with_session(
    db: AsyncSession, session, message: str, model: str | None
) -> dict:
    """基于会话的智能对话 — 带记忆和自动上下文压缩"""
    provider = await get_current_provider(db, session.user_id)
    if not provider:
        return {"error": "未配置当前 AI 提供商，请先在 AI 配置中设置"}

    use_model = model or session.model or provider.default_model

    # 构建系统提示
    system_prompt = (
        "你是一个专业的政策资讯分析助手。涉及资料的问题必须基于参考文章回答；"
        "寒暄、模型信息等一般问题直接简洁回答。"
        f"当前服务商为 {provider.name}，调用模型标识为 {use_model}。"
    )

    # 加入参考文章（基于关键词上下文）
    context = ""
    if session.keyword_id and _needs_article_context(message):
        context = await _gather_context(
            db,
            session.user_id,
            [],
            session.keyword_id,
            min(4_000, _context_limit(provider)),
            query_text=message,
        )
        if context:
            system_prompt += f"\n\n参考文章：\n{context}"

    # 加入记忆摘要
    if session.memory_summary:
        system_prompt += f"\n\n【对话记忆】\n{session.memory_summary}"

    # 构建消息列表
    messages = [{"role": "system", "content": system_prompt}]

    # 计算当前上下文总长度
    total_chars = len(system_prompt) + len(message)
    recent_messages = []

    # 取最近的消息，控制总长度
    history = [m for m in session.messages if m.role in ("user", "assistant")]
    for msg in reversed(history):
        msg_chars = len(msg.content)
        if total_chars + msg_chars > COMPRESS_THRESHOLD:
            break
        recent_messages.insert(0, {"role": msg.role, "content": msg.content})
        total_chars += msg_chars

    # 只保留最近几条
    if len(recent_messages) > KEEP_RECENT_MESSAGES:
        recent_messages = recent_messages[-KEEP_RECENT_MESSAGES:]

    messages.extend(recent_messages)
    messages.append({"role": "user", "content": message})

    compressed = False
    memory_summary = ""

    # 如果历史过长且未压缩，自动触发压缩
    if total_chars > COMPRESS_THRESHOLD and not session.context_compressed:
        memory_summary = await compress_session_context(db, session)
        compressed = True

    try:
        started_at = time.perf_counter()
        text = await chat_completion(
            provider.base_url, provider.api_key, use_model, messages, 0.7, 2048,
            provider.provider_key, provider.context_window,
        )
        result = {
            "reply": text,
            "model": use_model,
            "provider": provider.name,
            "provider_id": provider.id,
            "elapsed_ms": round((time.perf_counter() - started_at) * 1000),
            "context_chars": len(context),
        }
        if compressed:
            result["compressed"] = True
            result["memory_summary"] = memory_summary
        return result
    except AIProviderError as exc:
        return _provider_error(exc)

"""Observable keyword-driven discovery, extraction, deduplication, and storage."""
import asyncio
import hashlib
import io
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qsl, quote_plus, urlencode, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    CRAWLER_MAX_CONTENT_LENGTH,
    CRAWLER_MAX_FILE_SIZE,
    CRAWLER_MAX_RESULTS,
    CRAWLER_REQUEST_INTERVAL,
    CRAWLER_RETRIES,
    CRAWLER_RESPECT_ROBOTS_TXT,
    CRAWLER_ROBOTS_CACHE_SECONDS,
    CRAWLER_ROBOTS_FAIL_CLOSED,
    CRAWLER_ROBOTS_FAILURE_CACHE_SECONDS,
    CRAWLER_SEARCH_COOLDOWN_SECONDS,
    CRAWLER_SEARCH_REQUEST_INTERVAL,
    CRAWLER_TIMEOUT,
    CRAWLER_USER_AGENT,
    PDF_DIR,
)
from models import Article, ArticleKeyword, CrawlItem, CrawlLog, DataSource, Keyword, User

try:
    from pypdf import PdfReader
except ImportError:  # The crawler still stores PDFs and reports that extraction is unavailable.
    PdfReader = None


HEADERS = {
    "User-Agent": CRAWLER_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "spm", "from", "source", "ref", "track", "tracking", "sessionid",
}
GOV_SUFFIXES = (".gov.cn", ".gob.cn")
DATE_PATTERNS = (
    re.compile(r"(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?"),
    re.compile(r"(20\d{2})(\d{2})(\d{2})"),
)


class FetchError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class BlockedError(FetchError):
    pass


@dataclass
class DiscoveryBatch:
    items: list[dict] = field(default_factory=list)
    status: str = "success"
    error: str = ""
    http_status: int | None = None
    provider: str = ""
    stop_provider: bool = False


_last_request_at: dict[str, float] = {}

_SEARCH_HOSTS = {"www.bing.com", "bing.com", "www.baidu.com", "baidu.com"}
_bing_cooldown_until = 0.0
_bing_cooldown_reason = ""


def _bing_cooldown_remaining() -> int:
    return max(0, int(_bing_cooldown_until - time.monotonic()))


def _trip_bing_circuit(reason: str) -> None:
    global _bing_cooldown_until, _bing_cooldown_reason
    _bing_cooldown_until = time.monotonic() + CRAWLER_SEARCH_COOLDOWN_SECONDS
    _bing_cooldown_reason = reason


_baidu_cooldown_until = 0.0
_baidu_cooldown_reason = ""


def _baidu_cooldown_remaining() -> int:
    return max(0, int(_baidu_cooldown_until - time.monotonic()))


def _trip_baidu_circuit(reason: str) -> None:
    global _baidu_cooldown_until, _baidu_cooldown_reason
    _baidu_cooldown_until = time.monotonic() + CRAWLER_SEARCH_COOLDOWN_SECONDS
    _baidu_cooldown_reason = reason


# ---- robots.txt 缓存 ----
_robots_cache: dict[str, tuple["RobotsChecker", float]] = {}


class RobotsChecker:
    """轻量级 robots.txt 解析器，遵守 Robots Exclusion Standard。"""

    def __init__(self, base_url: str, rules_text: str = ""):
        self.base_url = base_url.rstrip("/")
        self.allowed_paths: list[str] = []
        self.disallowed_paths: list[str] = []
        self.has_rules = False
        if rules_text:
            self._parse(rules_text)

    def _parse(self, text: str) -> None:
        """解析 robots.txt 文本，提取 User-agent: * 下的规则。"""
        self.has_rules = True
        in_wildcard = False
        for raw_line in text.splitlines():
            line = raw_line.split("#")[0].strip()
            if not line:
                continue
            if ":" not in line:
                continue
            field, value = line.split(":", 1)
            field = field.strip().lower()
            value = value.strip()
            if field == "user-agent":
                in_wildcard = value == "*"
            elif field == "allow" and in_wildcard and value:
                self.allowed_paths.append(value)
            elif field == "disallow" and in_wildcard:
                if value:
                    self.disallowed_paths.append(value)
                # Disallow: (空值) 表示允许全部

    def is_allowed(self, url: str) -> bool:
        """检查 URL 是否被 robots.txt 允许抓取。"""
        if not self.has_rules:
            return True
        parsed = urlparse(url)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        matching_rules: list[tuple[int, bool]] = []
        for pattern in self.allowed_paths:
            if self._match(pattern, path):
                matching_rules.append((len(pattern.rstrip("$")), True))
        for pattern in self.disallowed_paths:
            if self._match(pattern, path):
                matching_rules.append((len(pattern.rstrip("$")), False))
        if not matching_rules:
            return True
        # RFC 9309 使用最具体的匹配；同等长度时 Allow 优先。
        return max(matching_rules, key=lambda item: (item[0], item[1]))[1]

    @staticmethod
    def _match(pattern: str, path: str) -> bool:
        """简单的 robots.txt 路径匹配（支持 * 和 $ 通配符）。"""
        if pattern == "/":
            return True
        anchored = pattern.endswith("$")
        raw_pattern = pattern[:-1] if anchored else pattern
        regex_pattern = re.escape(raw_pattern).replace(r"\*", ".*")
        suffix = "$" if anchored else ""
        return bool(re.match(f"^{regex_pattern}{suffix}", path))


async def _get_robots_checker(client: httpx.AsyncClient, url: str) -> RobotsChecker:
    """获取并缓存目标域名的 robots.txt 规则。"""
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    cached = _robots_cache.get(base_url)
    if cached and cached[1] > time.monotonic():
        return cached[0]

    robots_url = f"{base_url}/robots.txt"
    checker = RobotsChecker(base_url)
    cache_seconds = CRAWLER_ROBOTS_CACHE_SECONDS
    try:
        await _rate_limit(robots_url)
        response = await client.get(robots_url, timeout=10)
        if response.status_code == 200:
            checker = RobotsChecker(base_url, response.text)
            print(f"[Robots] 已加载 {robots_url}：{len(checker.disallowed_paths)} 条 Disallow 规则")
        elif response.status_code == 404:
            # 没有 robots.txt 表示全部允许
            checker.has_rules = False
        else:
            if CRAWLER_ROBOTS_FAIL_CLOSED:
                checker = RobotsChecker(base_url, "User-agent: *\nDisallow: /")
                cache_seconds = CRAWLER_ROBOTS_FAILURE_CACHE_SECONDS
                print(f"[Robots] 获取 {robots_url} 返回 HTTP {response.status_code}，按禁止处理")
            else:
                print(f"[Robots] 获取 {robots_url} 返回 HTTP {response.status_code}，按允许处理")
    except Exception as exc:
        if CRAWLER_ROBOTS_FAIL_CLOSED:
            checker = RobotsChecker(base_url, "User-agent: *\nDisallow: /")
            cache_seconds = CRAWLER_ROBOTS_FAILURE_CACHE_SECONDS
            print(f"[Robots] 获取 {robots_url} 失败：{exc}，按禁止处理")
        else:
            print(f"[Robots] 获取 {robots_url} 失败：{exc}，按允许处理")
            checker.has_rules = False

    _robots_cache[base_url] = (checker, time.monotonic() + cache_seconds)
    return checker


def canonicalize_url(url: str) -> str:
    """Normalize a URL for cross-keyword and cross-source deduplication."""
    url = (url or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    host = parsed.hostname.lower() if parsed.hostname else ""
    port = parsed.port
    netloc = host
    if port and not ((parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() not in TRACKING_PARAMS
    ]
    query.sort()
    return urlunparse((parsed.scheme.lower(), netloc, path, "", urlencode(query), ""))


def _hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _is_gov_url(url: str) -> bool:
    host = _hostname(url)
    return host == "gov.cn" or host.endswith(GOV_SUFFIXES)


def _is_pdf(url: str, content_type: str = "", content: bytes = b"") -> bool:
    clean_path = urlparse(url).path.lower()
    return clean_path.endswith(".pdf") or "application/pdf" in content_type.lower() or content.startswith(b"%PDF")


def _classify_source(url: str, is_pdf: bool, source_kind: str) -> str:
    if is_pdf:
        return "pdf"
    if source_kind == "official" or _is_gov_url(url):
        return "policy"
    if source_kind == "rss":
        return "news"
    return "document"


def _clean_text(text: str) -> str:
    text = re.sub(r"[\t\r\f\v]+", " ", text or "")
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_date(value: str) -> str:
    value = _clean_text(value)
    for pattern in DATE_PATTERNS:
        match = pattern.search(value)
        if match:
            year, month, day = match.groups()
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return value[:50]


def _terms(keyword: Keyword) -> list[str]:
    values = [keyword.keyword, *(keyword.aliases or []), *(keyword.exact_phrases or [])]
    seen = set()
    output = []
    for value in values:
        cleaned = value.strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            output.append(cleaned)
    return output


def _query_expression(keyword: Keyword) -> str:
    """Return a compact preview; discovery executes each positive term separately."""
    return " / ".join(_terms(keyword)[:5])


async def _selected_sources(
    keyword: Keyword, db: AsyncSession, override_source_ids: list[int] | None = None
) -> list[DataSource]:
    source_ids = override_source_ids or list(keyword.source_ids or [])
    query = select(DataSource).where(
        DataSource.user_id == keyword.user_id,
        DataSource.is_active == True,
    )
    if source_ids:
        query = query.where(DataSource.id.in_(source_ids))
    query = query.order_by(DataSource.priority, DataSource.id)
    return (await db.execute(query)).scalars().all()


async def build_query_plan(
    keyword: Keyword,
    db: AsyncSession,
    override_source_ids: list[int] | None = None,
) -> list[dict]:
    """Build the human-readable discovery plan shown in the UI and crawl log."""
    sources = await _selected_sources(keyword, db, override_source_ids)
    terms = _terms(keyword)[:5]
    expression = _query_expression(keyword)
    plan = []
    for source in sources:
        if source.source_kind == "official":
            domain = source.domain.strip() or _hostname(source.base_url)
            if not domain:
                continue
            for term in terms:
                plan.append({
                    "source_id": source.id,
                    "source_name": source.name,
                    "source_kind": source.source_kind,
                    "discovery_provider": "official_site",
                    "query": f'"{term}"',
                    "display_query": f'{source.name}官网原生检索："{term}"',
                    "required_domain": domain,
                    "term": term,
                    "limit": min(4, CRAWLER_MAX_RESULTS),  # 减少每个查询的结果数
                })
        elif source.source_kind == "rss":
            plan.append({
                "source_id": source.id,
                "source_name": source.name,
                "source_kind": source.source_kind,
                "discovery_provider": "rss",
                "query": expression,
                "feed_url": source.config.get("feed_url") or source.base_url,
                "limit": CRAWLER_MAX_RESULTS,
            })
        else:
            engine = source.config.get("engine", "bing") if hasattr(source, "config") else "bing"
            custom_sites = [site.strip() for site in (keyword.site_filters or []) if site.strip()]
            if custom_sites:
                for site in custom_sites[:5]:
                    for term in terms:
                        plan.append({
                            "source_id": source.id,
                            "source_name": source.name,
                            "source_kind": source.source_kind,
                            "discovery_provider": engine,
                            "query": f'site:{site} "{term}"',
                            "required_domain": site,
                            "term": term,
                            "limit": min(4, CRAWLER_MAX_RESULTS),  # 减少每个查询的结果数
                        })
            else:
                for term in terms:
                    plan.append({
                        "source_id": source.id,
                        "source_name": source.name,
                        "source_kind": source.source_kind,
                        "discovery_provider": engine,
                        "query": f'"{term}"',
                        "term": term,
                        "limit": CRAWLER_MAX_RESULTS,
                    })
    return plan


async def _rate_limit(url: str):
    host = _hostname(url)
    if not host:
        return
    # 搜索引擎使用更长间隔
    interval = (
        CRAWLER_SEARCH_REQUEST_INTERVAL
        if host in _SEARCH_HOSTS
        else CRAWLER_REQUEST_INTERVAL
    )
    elapsed = time.monotonic() - _last_request_at.get(host, 0)
    if elapsed < interval:
        await asyncio.sleep(interval - elapsed)
    _last_request_at[host] = time.monotonic()


async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(CRAWLER_RETRIES + 1):
        await _rate_limit(url)
        try:
            response = await client.get(url)
            if response.status_code in {401, 403, 407, 429}:
                raise BlockedError(
                    f"请求被限制，HTTP {response.status_code}", response.status_code
                )
            if response.status_code >= 500:
                raise FetchError(
                    f"目标站点暂时不可用，HTTP {response.status_code}", response.status_code
                )
            if response.status_code >= 400:
                raise FetchError(
                    f"请求失败，HTTP {response.status_code}", response.status_code
                )
            content_length = int(response.headers.get("content-length") or 0)
            if content_length > CRAWLER_MAX_FILE_SIZE:
                raise FetchError(f"文件超过大小限制：{content_length} bytes", response.status_code)
            return response
        except BlockedError:
            raise
        except (httpx.HTTPError, FetchError) as exc:
            last_error = exc
            if attempt < CRAWLER_RETRIES:
                await asyncio.sleep(0.6 * (2**attempt))
    status_code = getattr(last_error, "status_code", None)
    raise FetchError(f"网络请求失败：{last_error}", status_code)


def _bing_url(query: str, limit: int) -> str:
    return (
        "https://www.bing.com/search"
        f"?q={quote_plus(query)}&count={limit}&setlang=zh-CN"
    )


async def _discover_bing(
    client: httpx.AsyncClient, plan: dict, source: DataSource
) -> DiscoveryBatch:
    cooldown_remaining = _bing_cooldown_remaining()
    if cooldown_remaining:
        return DiscoveryBatch(
            status="blocked",
            error=(
                "Bing 搜索服务处于自动冷却期，已停止后续请求；"
                f"约 {cooldown_remaining // 60 + 1} 分钟后再试。"
                f"触发原因：{_bing_cooldown_reason}"
            ),
            provider="bing",
            stop_provider=True,
        )

    url = _bing_url(plan["query"], plan["limit"])
    try:
        search_headers = {
            **HEADERS,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        await _rate_limit(url)
        response = await client.get(url, headers=search_headers, follow_redirects=True)
        if response.status_code in {401, 403, 407, 429}:
            reason = f"HTTP {response.status_code}"
            _trip_bing_circuit(reason)
            return DiscoveryBatch(
                status="blocked",
                error=f"Bing 搜索服务限制访问（{reason}），已进入自动冷却期",
                http_status=response.status_code,
                provider="bing",
                stop_provider=True,
            )
        if response.status_code >= 400:
            return DiscoveryBatch(
                status="failed",
                error=f"Bing 搜索请求失败，HTTP {response.status_code}",
                http_status=response.status_code,
                provider="bing",
            )
        response.encoding = response.charset_encoding or "utf-8"
        html = response.text
        soup = BeautifulSoup(html, "lxml")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        blocked_markers = ("captcha", "unusual traffic", "验证您是真人", "验证码", "verify you are human")
        if any(marker.casefold() in html.casefold() for marker in blocked_markers):
            reason = f"验证页面：{title or '无页面标题'}"
            _trip_bing_circuit(reason)
            return DiscoveryBatch(
                status="blocked",
                error=f"Bing 搜索服务返回{reason}，已进入自动冷却期",
                http_status=response.status_code,
                provider="bing",
                stop_provider=True,
            )

        items = []
        for node in soup.select("#b_results > li.b_algo")[: plan["limit"]]:
            anchor = node.select_one("h2 a")
            if not anchor:
                continue
            item_url = canonicalize_url(anchor.get("href", ""))
            if not item_url or _hostname(item_url).endswith("bing.com"):
                continue
            required_domain = (plan.get("required_domain") or "").lower().lstrip(".")
            item_host = _hostname(item_url)
            if required_domain and not (
                item_host == required_domain or item_host.endswith(f".{required_domain}")
            ):
                continue
            snippet_node = node.select_one(".b_caption p, .b_lineclamp4, .b_paractl")
            date_node = node.select_one(".news_dt, .b_secondaryText")
            items.append({
                "title": anchor.get_text(" ", strip=True),
                "url": item_url,
                "snippet": snippet_node.get_text(" ", strip=True) if snippet_node else "",
                "publish_date": _normalize_date(date_node.get_text(" ", strip=True)) if date_node else "",
                "source_id": source.id,
                "source_name": source.name,
                "source_kind": source.source_kind,
                "matched_query": plan["query"],
            })

        if not items and not soup.select_one("#b_results"):
            reason = f"结果页结构异常：{title or '无页面标题'}"
            _trip_bing_circuit(reason)
            return DiscoveryBatch(
                status="blocked",
                error=f"Bing 搜索{reason}，已进入自动冷却期",
                http_status=response.status_code,
                provider="bing",
                stop_provider=True,
            )
        return DiscoveryBatch(items=items, http_status=response.status_code, provider="bing")
    except BlockedError as exc:
        _trip_bing_circuit(str(exc))
        return DiscoveryBatch(
            status="blocked",
            error=f"Bing 搜索服务限制访问：{exc}，已进入自动冷却期",
            http_status=exc.status_code,
            provider="bing",
            stop_provider=True,
        )
    except Exception as exc:
        return DiscoveryBatch(status="failed", error=str(exc), provider="bing")


def _baidu_url(query: str, limit: int) -> str:
    params = urlencode({"wd": query, "rn": str(min(limit, 20)), "ie": "utf-8"})
    return f"https://www.baidu.com/s?{params}"


async def _resolve_baidu_redirects(
    client: httpx.AsyncClient, items: list[dict], max_concurrency: int = 5
) -> None:
    """解析百度跳转链接（baidu.com/link?url=...），替换为真实目标 URL。"""
    redirect_indices = [
        i for i, item in enumerate(items)
        if "baidu.com/link" in item.get("url", "")
    ]
    if not redirect_indices:
        return

    semaphore = asyncio.Semaphore(max_concurrency)

    async def _resolve_one(idx: int) -> None:
        link_url = items[idx]["url"]
        async with semaphore:
            try:
                await asyncio.sleep(0.3)
                response = await client.get(
                    link_url, follow_redirects=False, timeout=10
                )
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location", "")
                    if location:
                        real_url = canonicalize_url(location) or location
                        if real_url:
                            items[idx]["url"] = real_url
            except Exception:
                pass  # 解析失败时保留原始跳转链接

    await asyncio.gather(*(_resolve_one(i) for i in redirect_indices))


async def _discover_baidu(
    client: httpx.AsyncClient, plan: dict, source: DataSource
) -> DiscoveryBatch:
    cooldown_remaining = _baidu_cooldown_remaining()
    if cooldown_remaining:
        return DiscoveryBatch(
            status="blocked",
            error=(
                "百度搜索服务处于自动冷却期，已停止后续请求；"
                f"约 {cooldown_remaining // 60 + 1} 分钟后再试。"
                f"触发原因：{_baidu_cooldown_reason}"
            ),
            provider="baidu",
            stop_provider=True,
        )

    url = _baidu_url(plan["query"], plan["limit"])
    try:
        search_headers = {
            **HEADERS,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        await _rate_limit(url)
        response = await client.get(url, headers=search_headers, follow_redirects=True)
        if response.status_code in {401, 403, 407, 429}:
            reason = f"HTTP {response.status_code}"
            _trip_baidu_circuit(reason)
            return DiscoveryBatch(
                status="blocked",
                error=f"百度搜索服务限制访问（{reason}），已进入自动冷却期",
                http_status=response.status_code,
                provider="baidu",
                stop_provider=True,
            )
        if response.status_code >= 400:
            return DiscoveryBatch(
                status="failed",
                error=f"百度搜索请求失败：HTTP {response.status_code}",
                http_status=response.status_code,
                provider="baidu",
            )
        response.encoding = response.charset_encoding or "utf-8"
        html = response.text
        soup = BeautifulSoup(html, "lxml")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""

        # 检查是否被重定向到验证页面（如 wappass.baidu.com）
        final_url = str(response.url)
        if any(marker in final_url for marker in ("wappass.baidu.com", "safecheck.baidu.com")):
            reason = f"重定向到验证页面：{final_url}"
            _trip_baidu_circuit(reason)
            return DiscoveryBatch(
                status="blocked",
                error=f"百度搜索{reason}，已进入自动冷却期",
                http_status=response.status_code,
                provider="baidu",
                stop_provider=True,
            )

        # 检查验证码/安全验证页面内容
        blocked_markers = ("百度安全验证", "验证码", "请完成验证", "wappass", "安全验证")
        if any(marker in html for marker in blocked_markers):
            reason = f"验证页面：{title or '无页面标题'}"
            _trip_baidu_circuit(reason)
            return DiscoveryBatch(
                status="blocked",
                error=f"百度搜索服务返回{reason}，已进入自动冷却期",
                http_status=response.status_code,
                provider="baidu",
                stop_provider=True,
            )

        items = []
        for node in soup.select("div.result, div.c-container")[: plan["limit"]]:
            anchor = node.select_one("h3 a")
            if not anchor:
                continue
            # 优先使用容器的 mu 属性获取真实 URL
            item_url = node.get("mu", "") or ""
            if not item_url:
                item_url = anchor.get("href", "")
            if not item_url:
                continue
            item_url = canonicalize_url(item_url) or item_url
            if not item_url:
                continue
            # 跳过百度自身页面（验证页、首页等），保留跳转链接待后续解析
            item_host = _hostname(item_url)
            if (
                item_host
                and item_host.endswith("baidu.com")
                and "baidu.com/link" not in item_url
            ):
                continue

            snippet_node = node.select_one(
                "span.content-right_8Zs40, .c-abstract, "
                "[class*='content-right'], .c-span-last"
            )
            snippet = snippet_node.get_text(" ", strip=True) if snippet_node else ""

            items.append({
                "title": anchor.get_text(" ", strip=True),
                "url": item_url,
                "snippet": snippet,
                "publish_date": "",
                "source_id": source.id,
                "source_name": source.name,
                "source_kind": source.source_kind,
                "matched_query": plan["query"],
            })

        # 解析百度跳转链接获取真实 URL
        await _resolve_baidu_redirects(client, items)

        if not items and not soup.select_one(
            "div#content_left, div.result, div.c-container"
        ):
            reason = f"结果页结构异常：{title or '无页面标题'}"
            _trip_baidu_circuit(reason)
            return DiscoveryBatch(
                status="blocked",
                error=f"百度搜索{reason}，已进入自动冷却期",
                http_status=response.status_code,
                provider="baidu",
                stop_provider=True,
            )
        return DiscoveryBatch(
            items=items, http_status=response.status_code, provider="baidu"
        )
    except BlockedError as exc:
        _trip_baidu_circuit(str(exc))
        return DiscoveryBatch(
            status="blocked",
            error=f"百度搜索服务限制访问：{exc}，已进入自动冷却期",
            http_status=exc.status_code,
            provider="baidu",
            stop_provider=True,
        )
    except httpx.HTTPError as exc:
        return DiscoveryBatch(
            status="failed",
            error=f"百度搜索网络请求失败：{type(exc).__name__}: {exc}",
            provider="baidu",
        )
    except FetchError as exc:
        return DiscoveryBatch(
            status="failed",
            error=f"百度搜索请求失败：{exc}",
            http_status=exc.status_code,
            provider="baidu",
        )
    except Exception as exc:
        return DiscoveryBatch(status="failed", error=str(exc), provider="baidu")


# ---- 政府网站站内搜索模板 ----
# type: "json_api" 表示直接调用 JSON API；"html" 表示解析 HTML 页面
_SITE_SEARCH_RULES: dict[str, dict] = {
    "nda.gov.cn": {
        "type": "pit_json_api",
        "url": "https://www.nda.gov.cn/admin/ams-service/openApi/open/sjj/3/ssapi/h5ss",
        "pit_path": "data.task_d3trpiyv8d5.master.0.data.id",
        "result_path": "data.task_d3trpiyv8d5.master.0.data.docs",
        "item_title": "title",
        "item_url": "url",
        "item_date": "time",
        "item_snippet": "content",
        "url_prefix": "https://www.nda.gov.cn",
    },
    "miit.gov.cn": {
        "type": "json_api",
        "url": "https://www.miit.gov.cn/search-front-server/api/search/info",
        "method": "GET",
        "params": {
            "websiteid": "110000000000000",
            "pageNo": "1",
            "pageSize": "20",
        },
        "q_param": "q",
        "result_path": "data.searchResult.dataResults",
        "item_title": "data.title",
        "item_url": "data.url",
        "item_date": "data.cdate",
        "item_display_date": "data.jsearch_date",
        "date_is_timestamp_ms": True,
        "url_prefix": "https://www.miit.gov.cn",
    },
}


def _get_site_search_rule(domain: str, source_config: dict | None = None) -> dict | None:
    """根据域名获取内置规则，也允许数据源配置覆盖或新增规则。"""
    configured_rule = (source_config or {}).get("search_rule")
    if isinstance(configured_rule, dict) and configured_rule.get("type"):
        return configured_rule
    domain = domain.lower().lstrip(".")
    for key, rule in _SITE_SEARCH_RULES.items():
        if domain == key or domain.endswith(f".{key}"):
            return rule
    return None


def _extract_nested(data: dict, path: str) -> list:
    """按点分路径提取嵌套数据"""
    result = _extract_value(data, path, [])
    return result if isinstance(result, list) else []


def _extract_value(data, path: str, default=None):
    """从字典和列表混合结构中读取点分路径。"""
    current = data
    for key in path.split("."):
        if isinstance(current, dict):
            current = current.get(key, default)
        elif isinstance(current, list) and key.isdigit():
            index = int(key)
            if index >= len(current):
                return default
            current = current[index]
        else:
            return default
        if current is default:
            return default
    return current


async def _discover_pit_json_api(
    client: httpx.AsyncClient,
    plan: dict,
    source: DataSource,
    domain: str,
    rule: dict,
    term: str,
    headers: dict,
) -> DiscoveryBatch:
    """执行国家数据局使用的公开 PIT 两阶段站内检索。"""
    provider = f"official:{domain}"
    open_payload = {"cmd": "open_pit", "params": {}}
    await _rate_limit(rule["url"])
    open_response = await client.post(
        rule["url"], json=open_payload, headers=headers, timeout=20
    )
    if open_response.status_code in {401, 403, 407, 429}:
        return DiscoveryBatch(
            status="blocked",
            error=f"站内搜索接口限制访问，HTTP {open_response.status_code}",
            http_status=open_response.status_code,
            provider=provider,
        )
    if open_response.status_code >= 400:
        return DiscoveryBatch(
            status="failed",
            error=f"站内搜索接口请求失败，HTTP {open_response.status_code}",
            http_status=open_response.status_code,
            provider=provider,
        )
    try:
        open_data = open_response.json()
    except Exception:
        return DiscoveryBatch(
            status="failed",
            error="站内搜索接口未返回有效的 PIT JSON",
            http_status=open_response.status_code,
            provider=provider,
        )

    pit_id = _extract_value(open_data, rule["pit_path"], "")
    if not pit_id:
        return DiscoveryBatch(
            status="failed",
            error="站内搜索接口未返回 PIT 标识",
            http_status=open_response.status_code,
            provider=provider,
        )

    search_payload = {
        "cmd": "search_global",
        "params": {
            "page": 1,
            "size": min(15, plan["limit"]),
            "sort": "_score",
            "pit_id": pit_id,
            "field": "title,category_name,time,url,source,content,_id",
            "key_place": "",
            "sub_docs": 1,
            "highlight": {"content": 200, "title": 50},
            "query": term,
        },
    }
    await _rate_limit(rule["url"])
    response = await client.post(
        rule["url"], json=search_payload, headers=headers, timeout=20
    )
    if response.status_code in {401, 403, 407, 429}:
        return DiscoveryBatch(
            status="blocked",
            error=f"站内搜索接口限制访问，HTTP {response.status_code}",
            http_status=response.status_code,
            provider=provider,
        )
    if response.status_code >= 400:
        return DiscoveryBatch(
            status="failed",
            error=f"站内搜索接口请求失败，HTTP {response.status_code}",
            http_status=response.status_code,
            provider=provider,
        )
    try:
        data = response.json()
    except Exception:
        return DiscoveryBatch(
            status="failed",
            error="站内搜索接口未返回有效 JSON",
            http_status=response.status_code,
            provider=provider,
        )

    items = []
    discovered_urls: set[str] = set()
    for document in _extract_nested(data, rule["result_path"])[: plan["limit"]]:
        url = str(_extract_value(document, rule["item_url"], "") or "")
        if rule.get("url_prefix") and url.startswith("/"):
            url = rule["url_prefix"] + url
        item_url = canonicalize_url(url)
        if not item_url or item_url in discovered_urls:
            continue
        item_host = _hostname(item_url)
        if not (item_host == domain or item_host.endswith(f".{domain}")):
            continue
        discovered_urls.add(item_url)

        title_html = str(_extract_value(document, rule["item_title"], "") or "")
        snippet_html = str(_extract_value(document, rule["item_snippet"], "") or "")
        title = BeautifulSoup(title_html, "lxml").get_text(" ", strip=True)
        snippet = BeautifulSoup(snippet_html, "lxml").get_text(" ", strip=True)
        publish_date = _normalize_date(
            str(_extract_value(document, rule["item_date"], "") or "")
        )
        items.append({
            "title": _clean_text(title),
            "url": item_url,
            "snippet": _clean_text(snippet)[:500],
            "publish_date": publish_date,
            "source_id": source.id,
            "source_name": source.name,
            "source_kind": source.source_kind,
            "matched_query": plan["query"],
        })

    print(f"[SiteSearch] {domain} PIT JSON API 搜索成功，发现 {len(items)} 条")
    return DiscoveryBatch(
        items=items,
        http_status=response.status_code,
        provider=provider,
    )


async def _discover_site_search(
    client: httpx.AsyncClient, plan: dict, source: DataSource, keyword: Keyword
) -> DiscoveryBatch:
    """通过政府网站站内搜索发现内容（不依赖外部搜索引擎）"""
    domain = (plan.get("required_domain") or source.domain or "").strip()
    if not domain:
        return DiscoveryBatch(status="failed", error="站内搜索需要域名")

    rule = _get_site_search_rule(domain, getattr(source, "config", {}))
    if not rule:
        # 无内置规则时，回退到 Bing site: 搜索
        term = plan.get("term") or keyword.keyword
        site_query = f'site:{domain} "{term}"'
        site_plan = {**plan, "query": site_query, "required_domain": domain}
        print(f"[SiteSearch] {domain} 无内置搜索规则，回退到 Bing site: 搜索")
        return await _discover_bing(client, site_plan, source)

    term = plan.get("term") or keyword.keyword

    try:
        # robots.txt 合规检查
        if CRAWLER_RESPECT_ROBOTS_TXT:
            try:
                checker = await _get_robots_checker(client, rule["url"])
                if not checker.is_allowed(rule["url"]):
                    return DiscoveryBatch(
                        status="blocked",
                        error=f"站内搜索被 robots.txt 禁止：{rule['url']}",
                    )
            except Exception as exc:
                print(f"[Robots] 检查站内搜索失败 {rule['url']}: {exc}")

        search_headers = {
            **HEADERS,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://www.{domain}/",
        }

        if rule.get("type") == "pit_json_api":
            return await _discover_pit_json_api(
                client, plan, source, domain, rule, term, search_headers
            )

        if rule.get("type") == "json_api":
            # ---- JSON API 模式 ----
            params = dict(rule.get("params", {}))
            params[rule.get("q_param", "q")] = term

            await _rate_limit(rule["url"])
            method = rule.get("method", "GET").upper()
            if method == "POST":
                response = await client.post(rule["url"], data=params, headers=search_headers, timeout=20)
            else:
                response = await client.get(rule["url"], params=params, headers=search_headers, timeout=20)

            if response.status_code in {401, 403, 407, 429}:
                return DiscoveryBatch(
                    status="blocked",
                    error=f"站内搜索接口限制访问，HTTP {response.status_code}",
                    http_status=response.status_code,
                    provider=f"official:{domain}",
                )
            if response.status_code >= 400:
                return DiscoveryBatch(
                    status="failed",
                    error=f"站内搜索接口请求失败，HTTP {response.status_code}",
                    http_status=response.status_code,
                    provider=f"official:{domain}",
                )

            import json as _json
            try:
                data = _json.loads(response.text)
            except Exception:
                return DiscoveryBatch(
                    status="failed",
                    error="站内搜索接口未返回有效 JSON",
                    http_status=response.status_code,
                    provider=f"official:{domain}",
                )

            if not data.get("success", True) and data.get("message"):
                return DiscoveryBatch(
                    status="failed",
                    error=f"站内搜索接口返回失败：{data.get('message')}",
                    http_status=response.status_code,
                    provider=f"official:{domain}",
                )

            results = _extract_nested(data, rule["result_path"])
            items = []
            discovered_urls: set[str] = set()
            url_prefix = rule.get("url_prefix", "")
            for result_item in results[: plan["limit"]]:
                item_data = result_item.get("data", result_item)
                title = item_data.get(rule["item_title"].split(".")[-1], "")
                url = item_data.get(rule["item_url"].split(".")[-1], "")
                if not url:
                    continue
                if url_prefix and url.startswith("/"):
                    url = url_prefix + url
                item_url = canonicalize_url(url)
                if not item_url or item_url in discovered_urls:
                    continue
                item_host = _hostname(item_url)
                if not (item_host == domain or item_host.endswith(f".{domain}")):
                    continue
                discovered_urls.add(item_url)

                publish_date = ""
                date_key = rule["item_date"].split(".")[-1] if rule.get("item_date") else ""
                display_date_key = rule.get("item_display_date", "").split(".")[-1]
                raw_date = item_data.get(display_date_key) or item_data.get(date_key)
                if raw_date:
                    if rule.get("date_is_timestamp_ms") and isinstance(raw_date, (int, float, str)):
                        try:
                            from datetime import datetime as _dt
                            ts = int(raw_date) / 1000
                            publish_date = _dt.fromtimestamp(ts).strftime("%Y-%m-%d")
                        except Exception:
                            publish_date = _normalize_date(str(raw_date))
                    else:
                        publish_date = _normalize_date(str(raw_date))

                items.append({
                    "title": _clean_text(title),
                    "url": item_url,
                    "snippet": _clean_text(item_data.get("content", ""))[:500] if item_data.get("content") else "",
                    "publish_date": publish_date,
                    "source_id": source.id,
                    "source_name": source.name,
                    "source_kind": source.source_kind,
                    "matched_query": plan["query"],
                })

            print(f"[SiteSearch] {domain} JSON API 搜索成功，发现 {len(items)} 条")
            return DiscoveryBatch(
                items=items,
                http_status=response.status_code,
                provider=f"official:{domain}",
            )

        else:
            # ---- HTML 解析模式（保留兼容） ----
            search_url = rule["url"].format(kw=quote_plus(term))
            await _rate_limit(search_url)
            response = await client.get(search_url, headers=HEADERS, follow_redirects=True, timeout=20)
            if response.status_code in {401, 403, 407, 429}:
                return DiscoveryBatch(
                    status="blocked",
                    error=f"站内搜索页面限制访问，HTTP {response.status_code}",
                    http_status=response.status_code,
                    provider=f"official:{domain}",
                )
            if response.status_code >= 400:
                return DiscoveryBatch(
                    status="failed",
                    error=f"站内搜索页面请求失败，HTTP {response.status_code}",
                    http_status=response.status_code,
                    provider=f"official:{domain}",
                )
            response.encoding = response.charset_encoding or "utf-8"
            html = response.text
            soup = BeautifulSoup(html, "lxml")

            # 检测 WAF 拦截
            title_text = soup.title.get_text(" ", strip=True) if soup.title else ""
            waf_markers = ("WAF", "防火墙", "访问防护", "触发系统", "intercept")
            if any(m.casefold() in html.casefold()[:3000] for m in waf_markers) and len(html) < 5000:
                return DiscoveryBatch(
                    status="blocked",
                    error=f"目标网站 WAF 拦截：{title_text}",
                    http_status=response.status_code,
                )

            items = []
            for node in soup.select(rule["item"])[: plan["limit"]]:
                anchor = node.select_one(rule["link"])
                if not anchor:
                    continue
                href = anchor.get("href", "")
                if not href:
                    continue
                item_url = canonicalize_url(urljoin(search_url, href))
                if not item_url:
                    continue
                item_host = _hostname(item_url)
                if not (item_host == domain or item_host.endswith(f".{domain}")):
                    continue
                title_node = node.select_one(rule["title"])
                snippet_node = node.select_one(rule["snippet"])
                date_node = node.select_one(rule["date"])
                items.append({
                    "title": title_node.get_text(" ", strip=True) if title_node else anchor.get_text(" ", strip=True),
                    "url": item_url,
                    "snippet": snippet_node.get_text(" ", strip=True) if snippet_node else "",
                    "publish_date": _normalize_date(date_node.get_text(" ", strip=True)) if date_node else "",
                    "source_id": source.id,
                    "source_name": source.name,
                    "source_kind": source.source_kind,
                    "matched_query": plan["query"],
                })

            print(f"[SiteSearch] {domain} HTML 搜索成功，发现 {len(items)} 条")
            return DiscoveryBatch(
                items=items,
                http_status=response.status_code,
                provider=f"official:{domain}",
            )

    except BlockedError as exc:
        return DiscoveryBatch(status="blocked", error=str(exc), http_status=exc.status_code)
    except Exception as exc:
        print(f"[SiteSearch] {domain} 站内搜索失败: {exc}")
        return DiscoveryBatch(
            status="failed",
            error=f"站内搜索失败：{exc}",
            provider=f"official:{domain}",
        )


def _xml_text(node: ET.Element | None, names: tuple[str, ...]) -> str:
    if node is None:
        return ""
    for child in list(node):
        local_name = child.tag.split("}")[-1].lower()
        if local_name in names:
            if local_name == "link" and child.attrib.get("href"):
                return child.attrib["href"].strip()
            return "".join(child.itertext()).strip()
    return ""


async def _discover_feed(
    client: httpx.AsyncClient, plan: dict, source: DataSource, keyword: Keyword
) -> DiscoveryBatch:
    feed_url = plan.get("feed_url", "")
    if not feed_url:
        return DiscoveryBatch(status="failed", error="RSS/Atom数据源未配置订阅地址")
    try:
        # robots.txt 合规检查 RSS 源
        if CRAWLER_RESPECT_ROBOTS_TXT:
            try:
                checker = await _get_robots_checker(client, feed_url)
                if not checker.is_allowed(feed_url):
                    return DiscoveryBatch(
                        status="blocked",
                        error=f"RSS 源被 robots.txt 禁止抓取：{feed_url}",
                    )
            except Exception as exc:
                print(f"[Robots] 检查 RSS 源失败 {feed_url}: {exc}")
        response = await _get(client, feed_url)
        root = ET.fromstring(response.content)
        nodes = [
            node for node in root.iter()
            if node.tag.split("}")[-1].lower() in {"item", "entry"}
        ]
        positive_terms = [term.casefold() for term in _terms(keyword)]
        excluded = [term.casefold() for term in (keyword.excluded_terms or [])]
        items = []
        for node in nodes:
            title = _xml_text(node, ("title",))
            link = _xml_text(node, ("link", "guid"))
            description = _xml_text(node, ("description", "summary", "content"))
            combined = f"{title} {description}".casefold()
            if not any(term in combined for term in positive_terms):
                continue
            if any(term in combined for term in excluded):
                continue
            item_url = canonicalize_url(urljoin(feed_url, link))
            if not item_url:
                continue
            date_value = _xml_text(node, ("pubdate", "published", "updated"))
            items.append({
                "title": title,
                "url": item_url,
                "snippet": _clean_text(BeautifulSoup(description, "lxml").get_text(" "))[:500],
                "publish_date": _normalize_date(date_value),
                "source_id": source.id,
                "source_name": source.name,
                "source_kind": source.source_kind,
                "matched_query": plan["query"],
            })
            if len(items) >= plan["limit"]:
                break
        return DiscoveryBatch(items=items, http_status=response.status_code)
    except BlockedError as exc:
        return DiscoveryBatch(status="blocked", error=str(exc), http_status=exc.status_code)
    except Exception as exc:
        return DiscoveryBatch(status="failed", error=f"订阅解析失败：{exc}")


async def _discover(
    client: httpx.AsyncClient, plan: dict, source: DataSource, keyword: Keyword
) -> DiscoveryBatch:
    if plan["source_kind"] == "rss":
        return await _discover_feed(client, plan, source, keyword)
    # official 数据源优先使用站内搜索（避免被搜索引擎限制）
    if plan["source_kind"] == "official" and plan.get("required_domain"):
        return await _discover_site_search(client, plan, source, keyword)
    # 根据配置选择搜索引擎
    engine = source.config.get("engine", "bing") if hasattr(source, "config") else "bing"
    if engine == "baidu":
        return await _discover_baidu(client, plan, source)
    return await _discover_bing(client, plan, source)


def _meta_content(soup: BeautifulSoup, keys: tuple[str, ...]) -> str:
    for key in keys:
        node = (
            soup.find("meta", attrs={"name": key})
            or soup.find("meta", attrs={"property": key})
            or soup.find("meta", attrs={"itemprop": key})
        )
        if node and node.get("content"):
            return node["content"].strip()
    return ""


def _extract_html(response: httpx.Response, fallback: dict) -> dict:
    response.encoding = response.charset_encoding or "utf-8"
    soup = BeautifulSoup(response.text, "lxml")
    title = _meta_content(soup, ("og:title", "twitter:title"))
    if not title:
        heading = soup.find("h1")
        title = heading.get_text(" ", strip=True) if heading else ""
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)
    title = _clean_text(title or fallback.get("title", ""))

    author = _meta_content(soup, ("author", "article:author", "byl"))
    publish_date = _meta_content(
        soup,
        (
            "publishdate", "publish_date", "pubdate", "date", "article:published_time",
            "weibo:article:create_at", "datePublished",
        ),
    )
    if not publish_date:
        time_node = soup.find("time")
        if time_node:
            publish_date = time_node.get("datetime") or time_node.get_text(" ", strip=True)
    if not publish_date:
        publish_date = fallback.get("publish_date", "")

    source_name = _meta_content(soup, ("source", "site_name", "og:site_name"))
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "iframe", "noscript"]):
        tag.decompose()

    selectors = (
        "article", "main", "#UCAP-CONTENT", ".TRS_Editor", ".pages_content",
        ".article", ".article-detail", ".detail-content", ".content",
        "[class*='article-content']", "[class*='article_content']",
        "[class*='content-body']", "[class*='main-content']",
    )
    candidates = []
    for selector in selectors:
        for node in soup.select(selector):
            paragraphs = [
                _clean_text(p.get_text(" ", strip=True))
                for p in node.find_all(["p", "h2", "h3", "li"])
            ]
            text = "\n".join(part for part in paragraphs if len(part) >= 15)
            raw_text = _clean_text(node.get_text("\n", strip=True))
            if len(raw_text) > len(text):
                text = raw_text
            if text:
                candidates.append(text)
    if candidates:
        content = max(candidates, key=len)
    else:
        paragraphs = [
            _clean_text(p.get_text(" ", strip=True))
            for p in soup.find_all("p")
        ]
        content = "\n".join(part for part in paragraphs if len(part) >= 20)
    content = _clean_text(content)[:CRAWLER_MAX_CONTENT_LENGTH]
    if len(content) < 80:
        snippet = _clean_text(fallback.get("snippet", ""))
        if len(snippet) > len(content):
            content = snippet

    attachments = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(str(response.url), anchor["href"])
        path = urlparse(href).path.lower()
        if path.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx")):
            attachments.append({
                "title": _clean_text(anchor.get_text(" ", strip=True)) or Path(path).name,
                "url": canonicalize_url(href) or href,
            })
        if len(attachments) >= 20:
            break

    return {
        "title": title[:500],
        "content": content,
        "author": _clean_text(author)[:200],
        "publish_date": _normalize_date(publish_date),
        "source_name": _clean_text(source_name)[:200] or _hostname(str(response.url)),
        "attachments": attachments,
        "ocr_required": False,
    }


def _extract_pdf_sync(data: bytes) -> dict:
    if PdfReader is None:
        return {
            "content": "",
            "author": "",
            "pdf_title": "",
            "page_count": 0,
            "ocr_required": True,
            "parser_warning": "未安装pypdf，已保存文件但未提取正文",
        }
    try:
        reader = PdfReader(io.BytesIO(data))
        parts = []
        total = 0
        for page in reader.pages:
            page_text = _clean_text(page.extract_text() or "")
            if page_text:
                remaining = CRAWLER_MAX_CONTENT_LENGTH - total
                parts.append(page_text[:remaining])
                total += len(parts[-1])
            if total >= CRAWLER_MAX_CONTENT_LENGTH:
                break
        metadata = reader.metadata or {}
        content = "\n\n".join(parts)
        return {
            "content": content,
            "author": str(metadata.get("/Author") or "")[:200],
            "pdf_title": str(metadata.get("/Title") or "")[:500],
            "page_count": len(reader.pages),
            "ocr_required": len(content) < 80,
            "parser_warning": "扫描型PDF，需要OCR" if len(content) < 80 else "",
        }
    except Exception as exc:
        return {
            "content": "",
            "author": "",
            "pdf_title": "",
            "page_count": 0,
            "ocr_required": True,
            "parser_warning": f"PDF解析失败：{exc}",
        }


def _content_hash(title: str, content: str, binary: bytes = b"") -> str:
    if binary:
        return hashlib.sha256(binary).hexdigest()
    normalized = re.sub(r"\s+", "", f"{title}\n{content}").casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def _relevance(keyword: Keyword, title: str, content: str, snippet: str) -> tuple[float, list[str]]:
    title_text = title.casefold()
    snippet_text = snippet.casefold()
    content_text = content.casefold()
    excluded = [term.strip() for term in (keyword.excluded_terms or []) if term.strip()]
    if any(term.casefold() in f"{title_text} {snippet_text} {content_text[:5000]}" for term in excluded):
        return -100, []
    score = 0.0
    matched = []
    for term in _terms(keyword):
        needle = term.casefold()
        term_score = 0.0
        if needle in title_text:
            term_score += 6
        if needle in snippet_text:
            term_score += 2
        if needle in content_text:
            term_score += 1
        if term_score:
            matched.append(term)
            score += term_score
    return score, matched


async def _find_existing(
    db: AsyncSession, user_id: int, canonical_url: str, content_hash: str = ""
) -> Article | None:
    clauses = [Article.canonical_url == canonical_url, Article.source_url == canonical_url]
    if content_hash:
        clauses.append(Article.content_hash == content_hash)
    result = await db.execute(
        select(Article).where(Article.user_id == user_id, or_(*clauses)).limit(1)
    )
    return result.scalars().first()


async def _link_keyword(
    db: AsyncSession,
    article_id: int,
    keyword_id: int,
    matched_query: str,
    relevance_score: float,
):
    existing = await db.get(ArticleKeyword, (article_id, keyword_id))
    if not existing:
        db.add(ArticleKeyword(
            article_id=article_id,
            keyword_id=keyword_id,
            matched_query=matched_query[:500],
            relevance_score=relevance_score,
        ))


async def _save_pdf(data: bytes, title: str, content_hash: str, user_id: int) -> str:
    safe_title = re.sub(r'[\\/*?:"<>|]', "_", title).strip(" .")[:70] or "document"
    user_dir = PDF_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    path = user_dir / f"{content_hash[:16]}_{safe_title}.pdf"
    if not path.exists():
        await asyncio.to_thread(path.write_bytes, data)
    return str(path)


async def _archive_first_pdf_attachment(
    client: httpx.AsyncClient,
    attachments: list[dict],
    fallback_title: str,
    user_id: int,
) -> dict | None:
    """Archive the first reachable PDF attachment without failing its parent page."""
    for attachment in attachments:
        attachment_url = canonicalize_url(attachment.get("url", ""))
        if not attachment_url or not urlparse(attachment_url).path.lower().endswith(".pdf"):
            continue
        try:
            response = await _get(client, attachment_url)
            data = response.content
            content_type = response.headers.get("content-type", "")
            if not _is_pdf(attachment_url, content_type, data):
                attachment["archive_status"] = "failed"
                attachment["archive_error"] = "附件响应不是PDF文件"
                continue
            digest = _content_hash("", "", data)
            attachment_title = attachment.get("title") or fallback_title
            path = await _save_pdf(data, attachment_title, digest, user_id)
            parsed = await asyncio.to_thread(_extract_pdf_sync, data)
            attachment.update({
                "archive_status": "saved",
                "file_size": len(data),
                "page_count": parsed.get("page_count", 0),
                "ocr_required": parsed.get("ocr_required", False),
                "parser_warning": parsed.get("parser_warning", ""),
            })
            return {
                "file_path": path,
                "file_size": len(data),
                "mime_type": content_type.split(";")[0] or "application/pdf",
                "content": parsed.get("content", ""),
                "attachment": dict(attachment),
            }
        except Exception as exc:
            attachment["archive_status"] = "failed"
            attachment["archive_error"] = str(exc)[:500]
    return None


async def _process_item(
    client: httpx.AsyncClient,
    db: AsyncSession,
    keyword: Keyword,
    log: CrawlLog,
    source: DataSource,
    discovered: dict,
):
    canonical_url = canonicalize_url(discovered["url"])
    item = CrawlItem(
        crawl_log_id=log.id,
        source_id=source.id,
        title=discovered.get("title", "")[:500],
        url=discovered["url"][:1500],
        canonical_url=canonical_url[:1500],
        status="discovered",
        stage="discovery",
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    item_id = item.id
    log_id = log.id

    existing = await _find_existing(db, keyword.user_id, canonical_url)
    if existing:
        score, _ = _relevance(
            keyword, existing.title, existing.content, discovered.get("snippet", "")
        )
        await _link_keyword(
            db, existing.id, keyword.id, discovered.get("matched_query", ""), score
        )
        item.article_id = existing.id
        item.status = "duplicate"
        item.stage = "deduplication"
        log.duplicate_count += 1
        await db.commit()
        return

    # robots.txt 合规检查
    if CRAWLER_RESPECT_ROBOTS_TXT:
        try:
            checker = await _get_robots_checker(client, canonical_url)
            if not checker.is_allowed(canonical_url):
                item.status = "blocked"
                item.stage = "robots"
                item.error_message = "URL 被 robots.txt 禁止抓取"
                log.failed_count += 1
                await db.commit()
                return
        except Exception as exc:
            print(f"[Robots] 检查失败 {canonical_url}: {exc}")

    try:
        item.stage = "fetch"
        response = await _get(client, canonical_url)
        item.http_status = response.status_code
        log.fetched_count += 1
        await db.commit()

        content_type = response.headers.get("content-type", "")
        binary = response.content
        if len(binary) > CRAWLER_MAX_FILE_SIZE:
            raise FetchError(f"响应超过大小限制：{len(binary)} bytes", response.status_code)
        is_pdf = _is_pdf(canonical_url, content_type, binary)

        item.stage = "parse"
        if is_pdf:
            parsed = await asyncio.to_thread(_extract_pdf_sync, binary)
            title = discovered.get("title", "") or parsed.get("pdf_title") or Path(urlparse(canonical_url).path).stem
            content = parsed.get("content", "") or discovered.get("snippet", "")
            author = parsed.get("author", "")
            publish_date = discovered.get("publish_date", "")
            source_name = _hostname(canonical_url) or source.name
            extra_metadata = {
                "page_count": parsed.get("page_count", 0),
                "ocr_required": parsed.get("ocr_required", False),
                "parser_warning": parsed.get("parser_warning", ""),
                "discovery_source": source.name,
                "matched_query": discovered.get("matched_query", ""),
            }
            digest = _content_hash(title, content, binary)
        else:
            parsed = _extract_html(response, discovered)
            title = parsed["title"] or discovered.get("title", "")
            content = parsed["content"]
            author = parsed["author"]
            publish_date = parsed["publish_date"]
            source_name = parsed["source_name"] or source.name
            extra_metadata = {
                "attachments": parsed.get("attachments", []),
                "discovery_source": source.name,
                "matched_query": discovered.get("matched_query", ""),
            }
            digest = _content_hash(title, content)
        log.parsed_count += 1

        score, matched_terms = _relevance(
            keyword, title, content, discovered.get("snippet", "")
        )
        if score <= 0:
            item.status = "rejected"
            item.stage = "relevance"
            item.error_message = "正文与关键词策略不匹配"
            log.rejected_count += 1
            await db.commit()
            return

        # 时间过滤：只保留最近 N 天的文章，0 表示不过滤
        date_range_days = getattr(keyword, "date_range_days", 0) or 0
        if date_range_days > 0 and publish_date:
            normalized_date = _normalize_date(publish_date)
            try:
                article_date = datetime.strptime(normalized_date[:10], "%Y-%m-%d")
            except ValueError:
                article_date = None
            if article_date:
                cutoff = datetime.now() - timedelta(days=date_range_days)
                if article_date < cutoff:
                    item.status = "rejected"
                    item.stage = "date_filter"
                    item.error_message = (
                        f"文章发布日期 {normalized_date} 超出最近 {date_range_days} 天范围"
                    )
                    log.rejected_count += 1
                    await db.commit()
                    return

        file_path = None
        file_type = ""
        file_size = 0
        stored_mime_type = content_type.split(";")[0][:100]
        if not is_pdf:
            archived = await _archive_first_pdf_attachment(
                client, extra_metadata.get("attachments", []), title, keyword.user_id
            )
            if archived:
                file_path = archived["file_path"]
                file_type = "pdf"
                file_size = archived["file_size"]
                stored_mime_type = archived["mime_type"][:100]
                extra_metadata["archived_attachment"] = archived["attachment"]
                attachment_content = archived.get("content", "")
                if attachment_content:
                    content = _clean_text(
                        f"{content}\n\n【附件正文】\n{attachment_content}"
                    )[:CRAWLER_MAX_CONTENT_LENGTH]
                    digest = _content_hash(title, content)

        duplicate = await _find_existing(db, keyword.user_id, canonical_url, digest)
        if duplicate:
            await _link_keyword(
                db, duplicate.id, keyword.id, discovered.get("matched_query", ""), score
            )
            item.article_id = duplicate.id
            item.status = "duplicate"
            item.stage = "deduplication"
            log.duplicate_count += 1
            await db.commit()
            return

        if is_pdf:
            file_path = await _save_pdf(binary, title, digest, keyword.user_id)
            file_type = "pdf"
            file_size = len(binary)

        article = Article(
            user_id=keyword.user_id,
            keyword_id=keyword.id,
            title=title[:500],
            content=content[:CRAWLER_MAX_CONTENT_LENGTH],
            summary="",
            source_url=canonical_url,
            canonical_url=canonical_url,
            content_hash=digest,
            source_name=source_name[:200],
            source_type=_classify_source(canonical_url, is_pdf, source.source_kind),
            author=author[:200],
            publish_date=_normalize_date(publish_date),
            file_path=file_path,
            file_type=file_type,
            mime_type=stored_mime_type,
            file_size=file_size,
            tags=",".join(matched_terms)[:500],
            extra_metadata=extra_metadata,
        )
        db.add(article)
        await db.flush()
        await _link_keyword(
            db, article.id, keyword.id, discovered.get("matched_query", ""), score
        )
        item.article_id = article.id
        item.status = "saved"
        item.stage = "persistence"
        log.saved_count += 1
        await db.commit()
    except BlockedError as exc:
        await db.rollback()
        item = await db.get(CrawlItem, item_id)
        log = await db.get(CrawlLog, log_id)
        item.status = "blocked"
        item.stage = "fetch"
        item.http_status = exc.status_code
        item.error_message = str(exc)
        log.failed_count += 1
        await db.commit()
    except Exception as exc:
        await db.rollback()
        item = await db.get(CrawlItem, item_id)
        log = await db.get(CrawlLog, log_id)
        item.status = "failed"
        item.error_message = str(exc)[:2000]
        log.failed_count += 1
        await db.commit()


def _final_status(log: CrawlLog, source_errors: list[tuple[str, str]]) -> str:
    if log.saved_count or log.duplicate_count:
        return "partial" if log.failed_count or source_errors else "success"
    if log.found_count == 0:
        if any(status == "blocked" for status, _ in source_errors):
            return "blocked"
        if source_errors:
            return "failed"
        return "empty"
    if log.failed_count:
        return "failed"
    return "empty"


async def crawl_keyword(
    keyword_id: int,
    db: AsyncSession,
    log_id: int | None = None,
    source_ids: list[int] | None = None,
    user_id: int | None = None,
) -> dict:
    """Execute one keyword strategy and persist stage-level diagnostics."""
    query = select(Keyword).where(Keyword.id == keyword_id)
    if user_id is not None:
        query = query.where(Keyword.user_id == user_id)
    keyword = (await db.execute(query)).scalars().first()
    if not keyword:
        raise ValueError(f"关键词不存在：{keyword_id}")

    keyword_snapshot = SimpleNamespace(
        id=keyword.id,
        user_id=keyword.user_id,
        keyword=keyword.keyword,
        aliases=list(keyword.aliases or []),
        exact_phrases=list(keyword.exact_phrases or []),
        excluded_terms=list(keyword.excluded_terms or []),
        site_filters=list(keyword.site_filters or []),
        source_ids=list(keyword.source_ids or []),
        date_range_days=getattr(keyword, "date_range_days", 7),
    )

    log = await db.get(CrawlLog, log_id) if log_id else None
    if not log:
        log = CrawlLog(
            user_id=keyword.user_id,
            keyword_id=keyword.id,
            keyword_text=keyword.keyword,
            status="pending",
            source_ids=source_ids or list(keyword.source_ids or []),
            started_at=datetime.now(),
        )
        db.add(log)
        await db.commit()
        await db.refresh(log)

    if log.user_id != keyword.user_id:
        raise ValueError("采集任务与关键词不属于同一用户")
    job_log_id = log.id

    log.status = "running"
    log.started_at = datetime.now()
    log.error_message = ""
    plan = await build_query_plan(keyword_snapshot, db, source_ids)
    log.query_plan = plan
    await db.commit()

    sources = await _selected_sources(keyword_snapshot, db, source_ids)
    source_map = {
        source.id: SimpleNamespace(
            id=source.id,
            name=source.name,
            source_kind=source.source_kind,
            base_url=source.base_url,
            domain=source.domain,
            config=dict(source.config or {}),
        )
        for source in sources
    }
    seen_urls: set[str] = set()
    source_errors: list[tuple[str, str]] = []
    reported_errors: set[tuple[str, str]] = set()
    stopped_providers: set[str] = set()

    timeout = httpx.Timeout(CRAWLER_TIMEOUT, connect=min(15, CRAWLER_TIMEOUT))
    limits = httpx.Limits(max_connections=5, max_keepalive_connections=3)
    async with httpx.AsyncClient(
        timeout=timeout,
        headers=HEADERS,
        follow_redirects=True,
        limits=limits,
        trust_env=True,
    ) as client:
        for plan_item in plan:
            if len(seen_urls) >= CRAWLER_MAX_RESULTS:
                break
            source = source_map.get(plan_item["source_id"])
            if not source:
                continue
            planned_provider = (
                plan_item.get("discovery_provider", "bing")
                if plan_item["source_kind"] == "search"
                else ""
            )
            if planned_provider and planned_provider in stopped_providers:
                continue
            batch = await _discover(client, plan_item, source, keyword_snapshot)
            await db.execute(
                update(DataSource)
                .where(
                    DataSource.id == source.id,
                    DataSource.user_id == keyword_snapshot.user_id,
                )
                .values(last_checked_at=datetime.now())
            )
            if batch.stop_provider and batch.provider:
                stopped_providers.add(batch.provider)
            if batch.status != "success":
                error_key = (batch.provider or source.name, batch.error)
                if error_key not in reported_errors:
                    reported_errors.add(error_key)
                    if batch.provider == "bing":
                        provider_name = "Bing 通用搜索"
                    elif batch.provider == "baidu":
                        provider_name = "百度通用搜索"
                    elif batch.provider.startswith("official:"):
                        provider_name = "官网原生发现"
                    else:
                        provider_name = batch.provider or source.source_kind
                    source_errors.append((
                        batch.status,
                        f"内容来源：{source.name}；发现渠道：{provider_name}；{batch.error}",
                    ))
                await db.commit()
                continue

            for discovered in batch.items:
                if len(seen_urls) >= CRAWLER_MAX_RESULTS:
                    break
                canonical_url = canonicalize_url(discovered.get("url", ""))
                if not canonical_url or canonical_url in seen_urls:
                    continue
                seen_urls.add(canonical_url)
                log.found_count += 1
                await db.commit()
                await _process_item(client, db, keyword_snapshot, log, source, discovered)
                # A failed item rolls the session back and expires ORM instances.
                # Re-load by the scalar ID captured before processing to avoid an
                # implicit async lazy-load when accessing an expired ``log.id``.
                log = await db.get(CrawlLog, job_log_id)

    log = await db.get(CrawlLog, job_log_id)
    log.status = _final_status(log, source_errors)
    log.error_message = "\n".join(dict.fromkeys(message for _, message in source_errors))[:10000]
    log.finished_at = datetime.now()
    keyword = await db.get(Keyword, keyword_id)
    keyword.last_crawl_at = datetime.now()
    await db.commit()

    # 采集完成后发送邮件通知
    if log.saved_count > 0 and getattr(keyword, "notify_on_crawl", True):
        try:
            user = await db.get(User, keyword.user_id)
            if user and user.notify_on_crawl and user.email:
                total_count = (
                    await db.execute(
                        select(func.count(Article.id)).where(
                            Article.keyword_id == keyword_id,
                            Article.user_id == keyword.user_id,
                        )
                    )
                ).scalar() or 0
                from services.email_service import send_crawl_notification
                await send_crawl_notification(
                    user.email, keyword.keyword, log.saved_count, total_count
                )
        except Exception as exc:
            print(f"[Crawler] 发送通知失败: {exc}")

    return {
        "log_id": log.id,
        "status": log.status,
        "found": log.found_count,
        "saved": log.saved_count,
        "duplicates": log.duplicate_count,
        "failed": log.failed_count,
        "error": log.error_message,
    }


async def create_crawl_logs(
    db: AsyncSession,
    keyword_ids: list[int] | None = None,
    source_ids: list[int] | None = None,
    force: bool = False,
    user_id: int | None = None,
) -> tuple[list[int], list[int]]:
    """Create durable pending jobs and reject duplicate in-flight jobs."""
    query = select(Keyword).where(Keyword.is_active == True)
    if user_id is not None:
        query = query.where(Keyword.user_id == user_id)
    if keyword_ids:
        query = query.where(Keyword.id.in_(keyword_ids))
    keywords = (await db.execute(query.order_by(Keyword.id))).scalars().all()
    log_ids = []
    skipped = []
    for keyword in keywords:
        if not force:
            active = (
                await db.execute(
                    select(CrawlLog.id).where(
                        CrawlLog.keyword_id == keyword.id,
                        CrawlLog.user_id == keyword.user_id,
                        CrawlLog.status.in_(["pending", "running"]),
                    ).limit(1)
                )
            ).scalar()
            if active:
                skipped.append(keyword.id)
                continue
        log = CrawlLog(
            user_id=keyword.user_id,
            keyword_id=keyword.id,
            keyword_text=keyword.keyword,
            status="pending",
            source_ids=source_ids or list(keyword.source_ids or []),
            started_at=datetime.now(),
        )
        db.add(log)
        await db.flush()
        log_ids.append(log.id)
    await db.commit()
    return log_ids, skipped


async def execute_crawl_logs(log_ids: list[int], source_ids: list[int] | None = None):
    """Run queued local jobs sequentially to remain polite to source websites."""
    from database import async_session

    for log_id in log_ids:
        async with async_session() as db:
            log = await db.get(CrawlLog, log_id)
            if not log or not log.keyword_id:
                continue
            try:
                await crawl_keyword(
                    log.keyword_id, db, log_id, source_ids, user_id=log.user_id
                )
            except Exception as exc:
                await db.rollback()
                failed_log = await db.get(CrawlLog, log_id)
                if failed_log:
                    failed_log.status = "failed"
                    failed_log.error_message = f"任务执行失败：{exc}"[:10000]
                    failed_log.finished_at = datetime.now()
                    await db.commit()


async def crawl_all(db: AsyncSession, user_id: int | None = None) -> list[dict]:
    """Compatibility entry point used by older callers."""
    log_ids, _ = await create_crawl_logs(db, user_id=user_id)
    results = []
    for log_id in log_ids:
        log = await db.get(CrawlLog, log_id)
        results.append(
            await crawl_keyword(log.keyword_id, db, log_id, user_id=log.user_id)
        )
    return results

"""Pydantic API schemas."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Authentication ----------
class UserOut(ORMModel):
    id: int
    username: str
    display_name: str
    email: str = ""
    phone: str = ""
    avatar: str = ""
    email_verified: bool = False
    notify_on_crawl: bool = True
    admin_role: int = 0
    created_at: datetime


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=100)
    email: str = Field(default="", max_length=200)
    verification_code: str = Field(default="", max_length=10)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


class SendCodeRequest(BaseModel):
    email: str = Field(min_length=5, max_length=200)


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=20)
    notify_on_crawl: bool | None = None
    email_verification_code: str | None = Field(default=None, max_length=10)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


# ---------- Keywords ----------
class KeywordBase(BaseModel):
    keyword: str = Field(min_length=1, max_length=200)
    category: str = "通用"
    is_active: bool = True
    crawl_interval: int = Field(default=24, ge=1, le=720)
    date_range_days: int = Field(default=7, ge=0, le=365)
    aliases: list[str] = Field(default_factory=list)
    exact_phrases: list[str] = Field(default_factory=list)
    excluded_terms: list[str] = Field(default_factory=list)
    site_filters: list[str] = Field(default_factory=list)
    source_ids: list[int] = Field(default_factory=list)
    notify_on_crawl: bool = True


class KeywordCreate(KeywordBase):
    pass


class KeywordUpdate(BaseModel):
    keyword: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = None
    is_active: bool | None = None
    crawl_interval: int | None = Field(default=None, ge=1, le=720)
    date_range_days: int | None = Field(default=None, ge=0, le=365)
    aliases: list[str] | None = None
    exact_phrases: list[str] | None = None
    excluded_terms: list[str] | None = None
    site_filters: list[str] | None = None
    source_ids: list[int] | None = None
    notify_on_crawl: bool | None = None


class KeywordOut(KeywordBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    last_crawl_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    article_count: int = 0


class QueryPreview(BaseModel):
    queries: list[dict[str, Any]]


# ---------- Data sources ----------
class DataSourceBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source_kind: str = Field(pattern="^(official|rss|search)$")
    base_url: str = ""
    domain: str = ""
    priority: int = Field(default=50, ge=1, le=999)
    is_active: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class DataSourceCreate(DataSourceBase):
    pass


class DataSourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    source_kind: str | None = Field(default=None, pattern="^(official|rss|search)$")
    base_url: str | None = None
    domain: str | None = None
    priority: int | None = Field(default=None, ge=1, le=999)
    is_active: bool | None = None
    config: dict[str, Any] | None = None


class DataSourceOut(DataSourceBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ---------- Articles ----------
class ArticleOut(ORMModel):
    id: int
    keyword_id: int
    title: str
    content: str
    summary: str
    source_url: str
    canonical_url: str = ""
    source_name: str
    source_type: str
    author: str
    publish_date: str | None = None
    crawl_date: datetime
    file_path: str | None = None
    file_type: str
    mime_type: str = ""
    file_size: int
    is_read: bool
    is_starred: bool
    tags: str
    extra_metadata: dict[str, Any] = Field(default_factory=dict)
    keyword_text: str = ""
    keyword_ids: list[int] = Field(default_factory=list)
    keyword_texts: list[str] = Field(default_factory=list)


class ArticleListOut(BaseModel):
    total: int
    items: list[ArticleOut]


# ---------- AI providers ----------
class ProviderBase(BaseModel):
    name: str
    provider_key: str = "custom"
    provider_type: str = "custom"
    base_url: str
    api_key: str = ""
    default_model: str = ""
    context_window: int = 0


class ProviderCreate(ProviderBase):
    pass


class ProviderUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    default_model: str | None = None
    context_window: int | None = None
    is_active: bool | None = None


class ProviderOut(ProviderBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool
    is_current: bool
    extra_config: dict
    created_at: datetime


class PresetProviderOut(BaseModel):
    key: str
    name: str
    base_url: str
    type: str
    website: str
    description: str
    context_window: int


class PresetOrder(BaseModel):
    keys: list[str] = Field(default_factory=list)


class TestConnectionRequest(BaseModel):
    base_url: str
    api_key: str = ""


class ModelListRequest(BaseModel):
    base_url: str
    api_key: str = ""


class ChatRequest(BaseModel):
    message: str
    article_ids: list[int] = Field(default_factory=list)
    keyword_id: int | None = None
    model: str | None = None


# ---------- Analysis ----------
class AnalysisRequest(BaseModel):
    article_ids: list[int] = Field(default_factory=list)
    keyword_id: int | None = None
    model: str | None = None


class AnalysisResultOut(ORMModel):
    id: int
    article_id: int | None = None
    keyword_id: int | None = None
    analysis_type: str
    provider_id: int | None = None
    model: str
    result: dict
    created_at: datetime


# ---------- Dashboard ----------
class DashboardStats(BaseModel):
    keyword_count: int
    article_count: int
    unread_count: int
    starred_count: int
    pdf_count: int
    provider_count: int
    today_count: int
    recent_articles: list[ArticleOut] = Field(default_factory=list)
    type_distribution: dict[str, int] = Field(default_factory=dict)
    trend_data: list[dict[str, Any]] = Field(default_factory=list)
    keyword_distribution: list[dict[str, Any]] = Field(default_factory=list)


# ---------- Crawler ----------
class CrawlRequest(BaseModel):
    keyword_ids: list[int] = Field(default_factory=list)
    source_ids: list[int] = Field(default_factory=list)
    force: bool = False


class CrawlLogOut(ORMModel):
    id: int
    keyword_id: int | None = None
    keyword_text: str
    status: str
    source_ids: list[int] = Field(default_factory=list)
    query_plan: list = Field(default_factory=list)
    found_count: int
    fetched_count: int
    parsed_count: int
    saved_count: int
    duplicate_count: int
    rejected_count: int
    failed_count: int
    error_message: str
    started_at: datetime
    finished_at: datetime | None = None
    duration: float | None = None


class CrawlItemOut(ORMModel):
    id: int
    crawl_log_id: int
    source_id: int | None = None
    article_id: int | None = None
    title: str
    url: str
    canonical_url: str
    status: str
    stage: str
    http_status: int | None = None
    error_message: str
    created_at: datetime
    updated_at: datetime


# ---------- Chat Sessions ----------
class ChatSessionCreate(BaseModel):
    title: str = "新对话"
    keyword_id: int | None = None
    model: str | None = None


class ChatSessionUpdate(BaseModel):
    title: str | None = None
    keyword_id: int | None = None
    model: str | None = None


class ChatMessageOut(ORMModel):
    id: int
    session_id: int
    role: str
    content: str
    token_count: int
    created_at: datetime


class ChatSessionOut(ORMModel):
    id: int
    title: str
    keyword_id: int | None = None
    provider_id: int | None = None
    model: str
    memory_summary: str = ""
    context_compressed: bool = False
    is_active: bool
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ChatSessionDetail(ChatSessionOut):
    messages: list[ChatMessageOut] = Field(default_factory=list)


class SessionChatRequest(BaseModel):
    message: str
    model: str | None = None


# ---------- 权限管理 ----------
class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    daily_token_limit: int = Field(default=100_000, ge=0)
    monthly_token_limit: int = Field(default=3_000_000, ge=0)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    daily_token_limit: int | None = Field(default=None, ge=0)
    monthly_token_limit: int | None = Field(default=None, ge=0)


class RoleOut(ORMModel):
    id: int
    name: str
    description: str
    daily_token_limit: int
    monthly_token_limit: int
    created_at: datetime
    user_count: int = 0
    provider_count: int = 0


class UserRoleAssign(BaseModel):
    user_ids: list[int]
    role_id: int


class ProviderGrantCreate(BaseModel):
    provider_id: int
    role_id: int


class AdminUserOut(ORMModel):
    id: int
    username: str
    display_name: str
    email: str = ""
    admin_role: int = 0
    is_active: bool
    roles: list[dict] = Field(default_factory=list)
    created_at: datetime


class TokenUsageOut(BaseModel):
    user_id: int
    daily_used: int
    monthly_used: int
    daily_limit: int
    monthly_limit: int
    remaining_today: int
    remaining_this_month: int

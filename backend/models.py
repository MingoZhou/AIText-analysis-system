"""SQLAlchemy data models."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class User(Base):
    """A local account that owns every business record in the prototype."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), default="")
    email: Mapped[str] = mapped_column(String(200), default="", index=True)
    phone: Mapped[str] = mapped_column(String(20), default="")
    avatar: Mapped[str] = mapped_column(String(500), default="")
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_on_crawl: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    admin_role: Mapped[int] = mapped_column(Integer, default=0)  # 1=管理员, 0=普通用户
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class AuthSession(Base):
    """A revocable opaque bearer session. Only the token digest is stored."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ProviderPreference(Base):
    """Per-user presentation preferences for provider presets."""

    __tablename__ = "provider_preferences"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    preset_order: Mapped[list] = mapped_column(JSON, default=list)
    current_provider_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class Keyword(Base):
    """A core keyword plus its reusable query strategy."""

    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    keyword: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), default="通用")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    crawl_interval: Mapped[int] = mapped_column(Integer, default=24)
    date_range_days: Mapped[int] = mapped_column(Integer, default=7)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    exact_phrases: Mapped[list] = mapped_column(JSON, default=list)
    excluded_terms: Mapped[list] = mapped_column(JSON, default=list)
    site_filters: Mapped[list] = mapped_column(JSON, default=list)
    source_ids: Mapped[list] = mapped_column(JSON, default=list)
    notify_on_crawl: Mapped[bool] = mapped_column(Boolean, default=True)
    last_crawl_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    articles: Mapped[list["Article"]] = relationship(back_populates="keyword")


class DataSource(Base):
    """A discovery source: authoritative site, RSS/Atom feed, or web search."""

    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    base_url: Mapped[str] = mapped_column(String(1000), default="")
    domain: Mapped[str] = mapped_column(String(300), default="")
    priority: Mapped[int] = mapped_column(Integer, default=50)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Article(Base):
    """A normalized document. The legacy keyword_id stores its first match."""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("keywords.id"), index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(String(1000), default="")
    canonical_url: Mapped[str] = mapped_column(String(1000), default="", index=True)
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    source_name: Mapped[str] = mapped_column(String(200), default="")
    source_type: Mapped[str] = mapped_column(String(50), default="news")
    author: Mapped[str] = mapped_column(String(200), default="")
    publish_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    crawl_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_type: Mapped[str] = mapped_column(String(20), default="")
    mime_type: Mapped[str] = mapped_column(String(100), default="")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_starred: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[str] = mapped_column(String(500), default="")
    extra_metadata: Mapped[dict] = mapped_column(JSON, default=dict)

    keyword: Mapped["Keyword"] = relationship(back_populates="articles")
    keyword_links: Mapped[list["ArticleKeyword"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )


class ArticleKeyword(Base):
    """Many-to-many match between a normalized document and keyword strategies."""

    __tablename__ = "article_keywords"

    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), primary_key=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("keywords.id"), primary_key=True, index=True)
    matched_query: Mapped[str] = mapped_column(String(500), default="")
    relevance_score: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    article: Mapped["Article"] = relationship(back_populates="keyword_links")


class AIProvider(Base):
    """AI provider configuration."""

    __tablename__ = "ai_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(50), default="custom")
    provider_type: Mapped[str] = mapped_column(String(20), default="custom")
    base_url: Mapped[str] = mapped_column(String(500), default="")
    api_key: Mapped[str] = mapped_column(String(500), default="")
    default_model: Mapped[str] = mapped_column(String(200), default="")
    context_window: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    extra_config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class AnalysisResult(Base):
    """Persisted AI analysis result."""

    __tablename__ = "analysis_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    article_id: Mapped[int | None] = mapped_column(ForeignKey("articles.id"), nullable=True, index=True)
    keyword_id: Mapped[int | None] = mapped_column(ForeignKey("keywords.id"), nullable=True, index=True)
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str] = mapped_column(String(200), default="")
    prompt: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CrawlLog(Base):
    """One observable crawl job for one keyword strategy."""

    __tablename__ = "crawl_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    keyword_id: Mapped[int | None] = mapped_column(ForeignKey("keywords.id"), nullable=True, index=True)
    keyword_text: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    source_ids: Mapped[list] = mapped_column(JSON, default=list)
    query_plan: Mapped[list] = mapped_column(JSON, default=list)
    found_count: Mapped[int] = mapped_column(Integer, default=0)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    parsed_count: Mapped[int] = mapped_column(Integer, default=0)
    saved_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    items: Mapped[list["CrawlItem"]] = relationship(
        back_populates="log", cascade="all, delete-orphan"
    )


class CrawlItem(Base):
    """Per-URL trace for discovery, fetch, parse, deduplication, and persistence."""

    __tablename__ = "crawl_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    crawl_log_id: Mapped[int] = mapped_column(ForeignKey("crawl_logs.id"), index=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("data_sources.id"), nullable=True)
    article_id: Mapped[int | None] = mapped_column(ForeignKey("articles.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    url: Mapped[str] = mapped_column(String(1500), default="")
    canonical_url: Mapped[str] = mapped_column(String(1500), default="")
    status: Mapped[str] = mapped_column(String(30), default="discovered")
    stage: Mapped[str] = mapped_column(String(30), default="discovery")
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    log: Mapped["CrawlLog"] = relationship(back_populates="items")


class ChatSession(Base):
    """智能对话会话 — 支持多轮对话、记忆、上下文压缩"""

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), default="新对话")
    keyword_id: Mapped[int | None] = mapped_column(ForeignKey("keywords.id"), nullable=True)
    provider_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str] = mapped_column(String(200), default="")
    # 压缩后的记忆摘要 — 删除会话时一并删除
    memory_summary: Mapped[str] = mapped_column(Text, default="")
    context_compressed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan",
        order_by="ChatMessage.id",
    )


class ChatMessage(Base):
    """单条对话消息 — 随会话删除而删除"""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user / assistant / system
    content: Mapped[str] = mapped_column(Text, default="")
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    session: Mapped["ChatSession"] = relationship(back_populates="messages")


# ========== 权限管理 ==========

class Role(Base):
    """工厂角色 — 用于批量授权智能体"""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(500), default="")
    daily_token_limit: Mapped[int] = mapped_column(Integer, default=100_000)
    monthly_token_limit: Mapped[int] = mapped_column(Integer, default=3_000_000)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class UserRole(Base):
    """用户←→角色 多对多"""

    __tablename__ = "user_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ProviderGrant(Base):
    """智能体←→角色 授权关系"""

    __tablename__ = "provider_grants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("ai_providers.id"), nullable=False, index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class TokenUsageLog(Base):
    """每次 AI 调用的 token 消耗记录"""

    __tablename__ = "token_usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    provider_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    analysis_type: Mapped[str] = mapped_column(String(50), default="")  # summary/chat/chart/wordcloud
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

"""Database initialization and lightweight SQLite migrations."""
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import DB_URL, DEFAULT_DATA_SOURCES

engine = create_async_engine(DB_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Base(DeclarativeBase):
    pass


SQLITE_COLUMNS = {
    "users": {
        "email": "VARCHAR(200) NOT NULL DEFAULT ''",
        "phone": "VARCHAR(20) NOT NULL DEFAULT ''",
        "avatar": "VARCHAR(500) NOT NULL DEFAULT ''",
        "email_verified": "BOOLEAN NOT NULL DEFAULT 0",
        "notify_on_crawl": "BOOLEAN NOT NULL DEFAULT 1",
        "admin_role": "INTEGER NOT NULL DEFAULT 0",
    },
    "keywords": {
        "aliases": "JSON NOT NULL DEFAULT '[]'",
        "exact_phrases": "JSON NOT NULL DEFAULT '[]'",
        "excluded_terms": "JSON NOT NULL DEFAULT '[]'",
        "site_filters": "JSON NOT NULL DEFAULT '[]'",
        "source_ids": "JSON NOT NULL DEFAULT '[]'",
        "notify_on_crawl": "BOOLEAN NOT NULL DEFAULT 1",
        "date_range_days": "INTEGER NOT NULL DEFAULT 7",
    },
    "data_sources": {},
    "articles": {
        "canonical_url": "VARCHAR(1000) NOT NULL DEFAULT ''",
        "content_hash": "VARCHAR(64) NOT NULL DEFAULT ''",
        "mime_type": "VARCHAR(100) NOT NULL DEFAULT ''",
        "extra_metadata": "JSON NOT NULL DEFAULT '{}'",
    },
    "ai_providers": {},
    "analysis_results": {},
    "provider_preferences": {
        "current_provider_id": "INTEGER DEFAULT NULL",
    },
    "crawl_logs": {
        "source_ids": "JSON NOT NULL DEFAULT '[]'",
        "query_plan": "JSON NOT NULL DEFAULT '[]'",
        "fetched_count": "INTEGER NOT NULL DEFAULT 0",
        "parsed_count": "INTEGER NOT NULL DEFAULT 0",
        "duplicate_count": "INTEGER NOT NULL DEFAULT 0",
        "rejected_count": "INTEGER NOT NULL DEFAULT 0",
        "failed_count": "INTEGER NOT NULL DEFAULT 0",
    },
}


async def _migrate_sqlite(conn, admin_id: int):
    """Add columns introduced after the first prototype without dropping data."""
    if conn.dialect.name != "sqlite":
        return

    for table_name, columns in SQLITE_COLUMNS.items():
        if table_name == "users":
            continue  # users 表已在 init_db 中单独迁移
        result = await conn.exec_driver_sql(f"PRAGMA table_info({table_name})")
        existing = {row[1] for row in result.fetchall()}
        # users 表不需要 user_id 列（它本身就是用户表）
        if table_name != "users" and "user_id" not in existing:
            await conn.exec_driver_sql(
                f"ALTER TABLE {table_name} ADD COLUMN user_id INTEGER DEFAULT {admin_id}"
            )
            existing.add("user_id")
        for column_name, definition in columns.items():
            if column_name not in existing:
                await conn.exec_driver_sql(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
                )
        if table_name != "users":
            await conn.exec_driver_sql(
                f"UPDATE {table_name} SET user_id = {admin_id} WHERE user_id IS NULL"
            )
            await conn.exec_driver_sql(
                f"CREATE INDEX IF NOT EXISTS ix_{table_name}_user_id ON {table_name}(user_id)"
            )

    await conn.exec_driver_sql(
        "UPDATE articles SET canonical_url = source_url "
        "WHERE canonical_url IS NULL OR canonical_url = ''"
    )
    await conn.exec_driver_sql(
        "INSERT OR IGNORE INTO article_keywords "
        "(article_id, keyword_id, matched_query, relevance_score, created_at) "
        "SELECT id, keyword_id, '', 0, CURRENT_TIMESTAMP FROM articles"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_articles_canonical_url ON articles(canonical_url)"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_articles_content_hash ON articles(content_hash)"
    )
    await conn.exec_driver_sql(
        "UPDATE crawl_logs SET status = 'empty' "
        "WHERE status = 'success' AND found_count = 0 AND saved_count = 0"
    )
    await conn.exec_driver_sql(
        "UPDATE crawl_logs SET finished_at = started_at "
        "WHERE found_count = 0 AND saved_count = 0 "
        "AND finished_at IS NOT NULL "
        "AND (julianday(finished_at) - julianday(started_at)) * 24 BETWEEN 7.5 AND 8.5"
    )
    await conn.exec_driver_sql(
        "UPDATE articles SET crawl_date = ("
        "SELECT crawl_items.created_at FROM crawl_items "
        "WHERE crawl_items.article_id = articles.id "
        "ORDER BY crawl_items.id LIMIT 1"
        ") WHERE EXISTS ("
        "SELECT 1 FROM crawl_items WHERE crawl_items.article_id = articles.id "
        "AND (julianday(crawl_items.created_at) - julianday(articles.crawl_date)) * 24 "
        "BETWEEN 7.5 AND 8.5"
        ")"
    )


async def _ensure_admin() -> int:
    from models import User
    from services.auth_service import hash_password

    async with async_session() as session:
        admin = (
            await session.execute(select(User).where(func.lower(User.username) == "admin"))
        ).scalars().first()
        if not admin:
            admin = User(
                username="admin",
                display_name="管理员",
                password_hash=hash_password("zhou1999"),
                email="zmh655300@163.com",
                admin_role=1,
            )
            session.add(admin)
            await session.commit()
            await session.refresh(admin)
        else:
            # 确保现有 admin 账号有管理员权限和正确邮箱
            if not admin.admin_role or admin.admin_role == 0:
                admin.admin_role = 1
            if not admin.email:
                admin.email = "zmh655300@163.com"
            await session.commit()
        return admin.id


async def _seed_sources(user_id: int):
    from models import DataSource

    async with async_session() as session:
        # 按名称检查已有数据源，补充缺失的
        existing_names = {
            row[0]
            for row in (
                await session.execute(
                    select(DataSource.name).where(DataSource.user_id == user_id)
                )
            ).fetchall()
        }
        missing = [
            source
            for source in DEFAULT_DATA_SOURCES
            if source["name"] not in existing_names
        ]
        if not missing:
            return
        session.add_all(
            DataSource(user_id=user_id, **source) for source in missing
        )
        await session.commit()


async def _migrate_users_table(conn):
    """在 _ensure_admin 之前迁移 users 表，确保新列存在"""
    if conn.dialect.name != "sqlite":
        return
    result = await conn.exec_driver_sql("PRAGMA table_info(users)")
    existing = {row[1] for row in result.fetchall()}
    for column_name, definition in SQLITE_COLUMNS["users"].items():
        if column_name not in existing:
            await conn.exec_driver_sql(
                f"ALTER TABLE users ADD COLUMN {column_name} {definition}"
            )


async def init_db():
    """Create tables, migrate the prototype schema, and seed source presets."""
    # Ensure every mapped table is registered even when init_db is invoked directly.
    import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 先迁移 users 表，确保 _ensure_admin 能正常查询
        await _migrate_users_table(conn)
    admin_id = await _ensure_admin()
    async with engine.begin() as conn:
        await _migrate_sqlite(conn, admin_id)
    await _seed_sources(admin_id)


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()

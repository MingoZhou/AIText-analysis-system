"""权限服务 — 智能体授权检查 + Token 限额控制"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    AIProvider,
    ProviderGrant,
    Role,
    TokenUsageLog,
    User,
    UserRole,
)


def is_admin(user: User) -> bool:
    """判断用户是否为管理员"""
    return getattr(user, "admin_role", 0) == 1


async def get_user_role_ids(db: AsyncSession, user_id: int) -> list[int]:
    """获取用户的所有角色 ID"""
    result = await db.execute(
        select(UserRole.role_id).where(UserRole.user_id == user_id)
    )
    return [row[0] for row in result.fetchall()]


async def get_user_accessible_provider_ids(db: AsyncSession, user: User) -> list[int]:
    """获取用户有权使用的所有 Provider ID

    管理员：返回所有 Provider ID
    普通用户：返回通过角色授权的 Provider ID
    """
    if is_admin(user):
        result = await db.execute(select(AIProvider.id))
        return [row[0] for row in result.fetchall()]

    role_ids = await get_user_role_ids(db, user.id)
    if not role_ids:
        return []

    result = await db.execute(
        select(ProviderGrant.provider_id)
        .where(ProviderGrant.role_id.in_(role_ids))
        .distinct()
    )
    return [row[0] for row in result.fetchall()]


async def check_provider_access(db: AsyncSession, user: User, provider_id: int) -> bool:
    """检查用户是否有权使用指定的 Provider"""
    if is_admin(user):
        return True

    role_ids = await get_user_role_ids(db, user.id)
    if not role_ids:
        return False

    result = await db.execute(
        select(ProviderGrant).where(
            ProviderGrant.provider_id == provider_id,
            ProviderGrant.role_id.in_(role_ids),
        )
    )
    return result.scalars().first() is not None


async def get_user_token_limits(db: AsyncSession, user: User) -> tuple[int, int]:
    """获取用户的 Token 限额（日限、月限）

    管理员：返回 (-1, -1) 表示不限额
    普通用户：取用户所有角色中限额最高的
    """
    if is_admin(user):
        return (-1, -1)

    role_ids = await get_user_role_ids(db, user.id)
    if not role_ids:
        return (0, 0)

    result = await db.execute(
        select(
            func.max(Role.daily_token_limit),
            func.max(Role.monthly_token_limit),
        ).where(Role.id.in_(role_ids))
    )
    row = result.first()
    return (row[0] or 0, row[1] or 0)


async def get_user_token_usage(db: AsyncSession, user_id: int) -> tuple[int, int]:
    """获取用户今日和本月的 Token 用量"""
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    result = await db.execute(
        select(func.coalesce(func.sum(TokenUsageLog.total_tokens), 0))
        .where(
            TokenUsageLog.user_id == user_id,
            TokenUsageLog.created_at >= today_start,
        )
    )
    daily_used = result.scalar() or 0

    result = await db.execute(
        select(func.coalesce(func.sum(TokenUsageLog.total_tokens), 0))
        .where(
            TokenUsageLog.user_id == user_id,
            TokenUsageLog.created_at >= month_start,
        )
    )
    monthly_used = result.scalar() or 0

    return (daily_used, monthly_used)


async def check_token_quota(db: AsyncSession, user: User) -> tuple[bool, str]:
    """检查用户 Token 限额是否充足

    返回 (是否允许, 消息)
    """
    if is_admin(user):
        return (True, "")

    daily_limit, monthly_limit = await get_user_token_limits(db, user)
    daily_used, monthly_used = await get_user_token_usage(db, user.id)

    if daily_limit == 0:
        return (False, "您的角色未设置 Token 限额，请联系管理员")

    if daily_used >= daily_limit:
        return (False, f"今日 Token 用量已达上限（{daily_limit:,}），请明天再试或联系管理员")

    if monthly_used >= monthly_limit:
        return (False, f"本月 Token 用量已达上限（{monthly_limit:,}），请下月再试或联系管理员")

    return (True, "")


async def log_token_usage(
    db: AsyncSession,
    user_id: int,
    provider_id: int | None,
    analysis_type: str,
    prompt_tokens: int,
    completion_tokens: int,
):
    """记录一次 AI 调用的 Token 消耗"""
    total = prompt_tokens + completion_tokens
    log = TokenUsageLog(
        user_id=user_id,
        provider_id=provider_id,
        analysis_type=analysis_type,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total,
    )
    db.add(log)
    await db.flush()


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数"""
    return len(text) // 4 if text else 0


async def get_granted_providers_for_user(db: AsyncSession, user: User) -> list[dict]:
    """获取用户被授权的 Provider 列表（带角色信息）"""
    if is_admin(user):
        result = await db.execute(select(AIProvider))
        providers = result.scalars().all()
        return [
            {
                "id": p.id,
                "name": p.name,
                "provider_key": p.provider_key,
                "default_model": p.default_model,
                "is_current": p.is_current,
            }
            for p in providers
        ]

    role_ids = await get_user_role_ids(db, user.id)
    if not role_ids:
        return []

    result = await db.execute(
        select(AIProvider)
        .join(ProviderGrant, ProviderGrant.provider_id == AIProvider.id)
        .where(ProviderGrant.role_id.in_(role_ids))
        .distinct()
    )
    providers = result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "provider_key": p.provider_key,
            "default_model": p.default_model,
            "is_current": p.is_current,
        }
        for p in providers
    ]

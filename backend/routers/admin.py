"""管理员路由 — 角色管理、智能体授权、用户管理、Token 限额"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import (
    AIProvider,
    ProviderGrant,
    Role,
    TokenUsageLog,
    User,
    UserRole,
)
from schemas import (
    AdminUserOut,
    ProviderGrantCreate,
    RoleCreate,
    RoleOut,
    RoleUpdate,
    UserRoleAssign,
)
from services.auth_service import get_current_user
from services.permission_service import (
    get_user_token_limits,
    get_user_token_usage,
    is_admin,
)

router = APIRouter(prefix="/api/admin", tags=["管理员"])


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """管理员守卫 — 非管理员返回 403"""
    if not is_admin(current_user):
        raise HTTPException(403, "无管理员权限")
    return current_user


# ========== 角色管理 ==========

@router.get("/roles", response_model=list[RoleOut])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """获取所有角色"""
    result = await db.execute(select(Role).order_by(Role.created_at.desc()))
    roles = result.scalars().all()
    out = []
    for r in roles:
        user_count = await db.execute(
            select(func.count(UserRole.id)).where(UserRole.role_id == r.id)
        )
        provider_count = await db.execute(
            select(func.count(ProviderGrant.id)).where(ProviderGrant.role_id == r.id)
        )
        item = RoleOut.model_validate(r)
        item.user_count = user_count.scalar() or 0
        item.provider_count = provider_count.scalar() or 0
        out.append(item)
    return out


@router.post("/roles", response_model=RoleOut)
async def create_role(
    data: RoleCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """创建角色"""
    existing = await db.execute(select(Role).where(Role.name == data.name))
    if existing.scalars().first():
        raise HTTPException(409, "角色名已存在")
    role = Role(**data.model_dump())
    db.add(role)
    await db.commit()
    await db.refresh(role)
    item = RoleOut.model_validate(role)
    item.user_count = 0
    item.provider_count = 0
    return item


@router.put("/roles/{role_id}", response_model=RoleOut)
async def update_role(
    role_id: int,
    data: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """更新角色"""
    role = (await db.execute(select(Role).where(Role.id == role_id))).scalars().first()
    if not role:
        raise HTTPException(404, "角色不存在")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(role, field, value)
    await db.commit()
    await db.refresh(role)
    item = RoleOut.model_validate(role)
    uc = await db.execute(select(func.count(UserRole.id)).where(UserRole.role_id == role.id))
    pc = await db.execute(select(func.count(ProviderGrant.id)).where(ProviderGrant.role_id == role.id))
    item.user_count = uc.scalar() or 0
    item.provider_count = pc.scalar() or 0
    return item


@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """删除角色 — 同时清除用户绑定和智能体授权"""
    role = (await db.execute(select(Role).where(Role.id == role_id))).scalars().first()
    if not role:
        raise HTTPException(404, "角色不存在")
    await db.execute(
        select(UserRole).where(UserRole.role_id == role_id)
    )
    # 删除关联
    for ur in (await db.execute(select(UserRole).where(UserRole.role_id == role_id))).scalars().all():
        await db.delete(ur)
    for pg in (await db.execute(select(ProviderGrant).where(ProviderGrant.role_id == role_id))).scalars().all():
        await db.delete(pg)
    await db.delete(role)
    await db.commit()
    return {"message": f"角色「{role.name}」已删除"}


# ========== 用户-角色分配 ==========

@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """获取所有用户列表（含角色信息）"""
    result = await db.execute(
        select(User).order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    out = []
    for u in users:
        role_result = await db.execute(
            select(Role).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == u.id)
        )
        roles = [{"id": r.id, "name": r.name} for r in role_result.scalars().all()]
        item = AdminUserOut.model_validate(u)
        item.roles = roles
        out.append(item)
    return out


@router.post("/users/assign-roles")
async def assign_roles_to_user(
    data: UserRoleAssign,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """批量给用户分配角色（替换模式：先清除旧角色，再分配新角色）"""
    # 验证角色存在
    role = (await db.execute(select(Role).where(Role.id == data.role_id))).scalars().first()
    if not role:
        raise HTTPException(404, "角色不存在")

    # 删除这些用户在该角色下的旧记录（避免重复）
    for uid in data.user_ids:
        existing = await db.execute(
            select(UserRole).where(UserRole.user_id == uid, UserRole.role_id == data.role_id)
        )
        for ur in existing.scalars().all():
            await db.delete(ur)
        db.add(UserRole(user_id=uid, role_id=data.role_id))

    await db.commit()
    return {"message": f"已为 {len(data.user_ids)} 个用户分配角色「{role.name}」"}


@router.delete("/users/{user_id}/roles/{role_id}")
async def remove_user_role(
    user_id: int,
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """移除用户的某个角色"""
    ur = (
        await db.execute(
            select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)
        )
    ).scalars().first()
    if not ur:
        raise HTTPException(404, "该用户没有此角色")
    await db.delete(ur)
    await db.commit()
    return {"message": "已移除角色"}


# ========== 智能体授权 ==========

@router.get("/roles/{role_id}/providers")
async def list_role_providers(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """获取角色已授权的智能体 ID 列表"""
    result = await db.execute(
        select(ProviderGrant.provider_id).where(ProviderGrant.role_id == role_id)
    )
    return [row[0] for row in result.fetchall()]


@router.get("/providers/{provider_id}/grants")
async def list_provider_grants(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """获取某智能体的授权角色列表"""
    result = await db.execute(
        select(Role)
        .join(ProviderGrant, ProviderGrant.role_id == Role.id)
        .where(ProviderGrant.provider_id == provider_id)
    )
    roles = result.scalars().all()
    return [{"id": r.id, "name": r.name, "description": r.description} for r in roles]


@router.post("/providers/grants")
async def create_provider_grant(
    data: ProviderGrantCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """授权智能体给角色"""
    provider = (await db.execute(select(AIProvider).where(AIProvider.id == data.provider_id))).scalars().first()
    if not provider:
        raise HTTPException(404, "智能体不存在")
    role = (await db.execute(select(Role).where(Role.id == data.role_id))).scalars().first()
    if not role:
        raise HTTPException(404, "角色不存在")

    existing = (
        await db.execute(
            select(ProviderGrant).where(
                ProviderGrant.provider_id == data.provider_id,
                ProviderGrant.role_id == data.role_id,
            )
        )
    ).scalars().first()
    if existing:
        raise HTTPException(409, "该角色已授权此智能体")

    db.add(ProviderGrant(provider_id=data.provider_id, role_id=data.role_id))
    await db.commit()
    return {"message": f"已将「{provider.name}」授权给角色「{role.name}」"}


@router.delete("/providers/{provider_id}/grants/{role_id}")
async def delete_provider_grant(
    provider_id: int,
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """撤销智能体对角色的授权"""
    grant = (
        await db.execute(
            select(ProviderGrant).where(
                ProviderGrant.provider_id == provider_id,
                ProviderGrant.role_id == role_id,
            )
        )
    ).scalars().first()
    if not grant:
        raise HTTPException(404, "授权记录不存在")
    await db.delete(grant)
    await db.commit()
    return {"message": "已撤销授权"}


# ========== Token 用量查看 ==========

@router.get("/users/{user_id}/token-usage")
async def get_user_token_usage_admin(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """管理员查看某用户的 Token 用量"""
    user = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
    if not user:
        raise HTTPException(404, "用户不存在")

    daily_limit, monthly_limit = await get_user_token_limits(db, user)
    daily_used, monthly_used = await get_user_token_usage(db, user.id)

    return {
        "user_id": user.id,
        "username": user.username,
        "is_admin": is_admin(user),
        "daily_used": daily_used,
        "monthly_used": monthly_used,
        "daily_limit": daily_limit,
        "monthly_limit": monthly_limit,
        "remaining_today": max(daily_limit - daily_used, 0) if daily_limit > 0 else -1,
        "remaining_this_month": max(monthly_limit - monthly_used, 0) if monthly_limit > 0 else -1,
    }


@router.get("/token-usage/all")
async def get_all_token_usage(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """管理员查看所有用户的 Token 用量汇总"""
    result = await db.execute(
        select(User).where(User.is_active == True).order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    out = []
    for u in users:
        daily_limit, monthly_limit = await get_user_token_limits(db, u)
        daily_used, monthly_used = await get_user_token_usage(db, u.id)
        out.append({
            "user_id": u.id,
            "username": u.username,
            "display_name": u.display_name,
            "is_admin": is_admin(u),
            "daily_used": daily_used,
            "monthly_used": monthly_used,
            "daily_limit": daily_limit,
            "monthly_limit": monthly_limit,
        })
    return out

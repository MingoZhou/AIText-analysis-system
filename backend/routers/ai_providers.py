"""AI 提供商管理路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import LOCAL_PRESETS, PROVIDER_PRESETS
from database import get_db
from models import AIProvider, ProviderPreference, User
from schemas import (
    ModelListRequest,
    PresetOrder,
    PresetProviderOut,
    ProviderCreate,
    ProviderOut,
    ProviderUpdate,
    TestConnectionRequest,
)
from services.ai_service import AIProviderError, get_models, test_connection
from services.auth_service import get_current_user
from services.permission_service import is_admin

router = APIRouter(prefix="/api/providers", tags=["AI 提供商"])


async def _require_admin(user: User):
    """非管理员禁止配置操作"""
    if not is_admin(user):
        raise HTTPException(403, "仅管理员可配置智能体")


def _normalized_order(keys: list[str]) -> list[str]:
    available = [*PROVIDER_PRESETS.keys(), *LOCAL_PRESETS.keys()]
    seen = set()
    output = []
    for key in [*keys, *available]:
        if key in available and key not in seen:
            seen.add(key)
            output.append(key)
    return output


async def _get_order(db: AsyncSession, user_id: int) -> list[str]:
    preference = await db.get(ProviderPreference, user_id)
    return _normalized_order(preference.preset_order if preference else [])


@router.get("/presets", response_model=list[PresetProviderOut])
async def list_presets(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """获取预设供应商列表"""
    presets = []
    order = await _get_order(db, current_user.id)
    for key in order:
        info = PROVIDER_PRESETS.get(key)
        if not info:
            continue
        presets.append(PresetProviderOut(key=key, **info))
    return presets


@router.get("/local-presets", response_model=list[PresetProviderOut])
async def list_local_presets(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """获取本地部署预设"""
    presets = []
    order = await _get_order(db, current_user.id)
    for key in order:
        info = LOCAL_PRESETS.get(key)
        if not info:
            continue
        data = {**info, "website": ""}
        presets.append(PresetProviderOut(key=key, **data))
    return presets


@router.get("/preset-order", response_model=PresetOrder)
async def get_preset_order(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return PresetOrder(keys=await _get_order(db, current_user.id))


@router.put("/preset-order", response_model=PresetOrder)
async def update_preset_order(
    data: PresetOrder,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_admin(current_user)
    keys = _normalized_order(data.keys)
    preference = await db.get(ProviderPreference, current_user.id)
    if preference:
        preference.preset_order = keys
    else:
        db.add(ProviderPreference(user_id=current_user.id, preset_order=keys))
    await db.commit()
    return PresetOrder(keys=keys)


@router.get("", response_model=list[ProviderOut])
async def list_providers(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """获取已配置供应商列表

    管理员：返回所有
    普通用户：返回被授权的（通过角色），且隐藏敏感字段
    """
    if is_admin(current_user):
        result = await db.execute(
            select(AIProvider)
            .where(AIProvider.user_id == current_user.id)
            .order_by(AIProvider.created_at.desc())
        )
    else:
        # 普通用户：返回被授权的 Provider
        from services.permission_service import get_user_accessible_provider_ids
        accessible_ids = await get_user_accessible_provider_ids(db, current_user)
        if not accessible_ids:
            return []
        result = await db.execute(
            select(AIProvider)
            .where(AIProvider.id.in_(accessible_ids))
            .order_by(AIProvider.created_at.desc())
        )

    providers = result.scalars().all()
    # 普通用户：隐藏敏感字段并标记当前选择
    if not is_admin(current_user):
        pref = await db.get(ProviderPreference, current_user.id)
        current_id = pref.current_provider_id if pref else None
        for p in providers:
            p.api_key = ""
            p.base_url = ""
            p.is_current = (p.id == current_id)
    return providers


@router.post("", response_model=ProviderOut)
async def create_provider(
    data: ProviderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_admin(current_user)
    if data.provider_key != "custom":
        duplicate = (
            await db.execute(
                select(AIProvider).where(
                    AIProvider.user_id == current_user.id,
                    AIProvider.provider_key == data.provider_key,
                )
            )
        ).scalars().first()
        if duplicate:
            raise HTTPException(409, "该提供商已配置，请直接编辑现有配置")
    provider = AIProvider(user_id=current_user.id, **data.model_dump())
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return provider


@router.put("/{provider_id}", response_model=ProviderOut)
async def update_provider(
    provider_id: int,
    data: ProviderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_admin(current_user)
    provider = (
        await db.execute(
            select(AIProvider).where(
                AIProvider.id == provider_id,
                AIProvider.user_id == current_user.id,
            )
        )
    ).scalars().first()
    if not provider:
        raise HTTPException(404, "提供商不存在")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(provider, field, value)
    await db.commit()
    await db.refresh(provider)
    return provider


@router.delete("/{provider_id}")
async def delete_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_admin(current_user)
    provider = (
        await db.execute(
            select(AIProvider).where(
                AIProvider.id == provider_id,
                AIProvider.user_id == current_user.id,
            )
        )
    ).scalars().first()
    if not provider:
        raise HTTPException(404, "提供商不存在")
    await db.delete(provider)
    await db.commit()
    return {"message": "已删除"}


@router.put("/{provider_id}/current")
async def set_current_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """设为当前使用的提供商

    管理员：可设任意 Provider
    普通用户：只能设被授权的 Provider
    """
    from services.permission_service import check_provider_access

    if not is_admin(current_user):
        has_access = await check_provider_access(db, current_user, provider_id)
        if not has_access:
            raise HTTPException(403, "暂无权限使用此智能体，请联系管理员")

    # 查找 Provider
    if is_admin(current_user):
        provider = (
            await db.execute(
                select(AIProvider).where(
                    AIProvider.id == provider_id,
                    AIProvider.user_id == current_user.id,
                )
            )
        ).scalars().first()
    else:
        provider = (
            await db.execute(
                select(AIProvider).where(AIProvider.id == provider_id)
            )
        ).scalars().first()

    if not provider:
        raise HTTPException(404, "提供商不存在")

    # 管理员：取消自己名下其他 current
    if is_admin(current_user):
        result = await db.execute(
            select(AIProvider).where(
                AIProvider.user_id == current_user.id,
                AIProvider.is_current == True,
            )
        )
        for p in result.scalars().all():
            p.is_current = False
        provider.is_current = True
    else:
        # 普通用户：通过 ProviderPreference 记录当前选择
        preference = await db.get(ProviderPreference, current_user.id)
        if preference:
            preference.current_provider_id = provider.id
        else:
            db.add(ProviderPreference(
                user_id=current_user.id,
                current_provider_id=provider.id,
            ))

    await db.commit()
    return {"message": f"已设为当前提供商: {provider.name}"}


@router.post("/test")
async def test_provider_connection(
    request: TestConnectionRequest,
    current_user: User = Depends(get_current_user),
):
    """测试连接"""
    await _require_admin(current_user)
    return await test_connection(request.base_url, request.api_key)


@router.post("/models")
async def get_provider_models(
    request: ModelListRequest,
    current_user: User = Depends(get_current_user),
):
    """获取模型列表"""
    await _require_admin(current_user)
    try:
        models = await get_models(request.base_url, request.api_key)
        return {"models": models}
    except AIProviderError as exc:
        status = 502 if exc.retryable else 400
        raise HTTPException(status, {"message": str(exc), **exc.as_dict()}) from exc

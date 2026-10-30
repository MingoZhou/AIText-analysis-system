"""智能对话会话路由 — 会话管理 + 记忆 + 上下文压缩"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models import ChatMessage, ChatSession, User
from schemas import (
    ChatMessageOut,
    ChatSessionCreate,
    ChatSessionDetail,
    ChatSessionOut,
    ChatSessionUpdate,
    SessionChatRequest,
)
from services.ai_service import chat_with_session, compress_session_context, get_current_provider
from services.auth_service import get_current_user
from services.permission_service import (
    check_provider_access,
    check_token_quota,
    estimate_tokens,
    is_admin,
    log_token_usage,
)

router = APIRouter(prefix="/api/chat-sessions", tags=["智能对话"])


@router.get("", response_model=list[ChatSessionOut])
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取用户的对话列表"""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id, ChatSession.is_active == True)
        .order_by(ChatSession.updated_at.desc())
    )
    sessions = result.scalars().all()
    out = []
    for s in sessions:
        msg_count = await db.execute(
            select(func.count(ChatMessage.id)).where(ChatMessage.session_id == s.id)
        )
        item = ChatSessionOut.model_validate(s)
        item.message_count = msg_count.scalar() or 0
        out.append(item)
    return out


@router.post("", response_model=ChatSessionDetail)
async def create_session(
    body: ChatSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新建对话"""
    provider = await get_current_provider(db, current_user.id)
    session = ChatSession(
        user_id=current_user.id,
        title=body.title or "新对话",
        keyword_id=body.keyword_id,
        model=body.model or (provider.default_model if provider else ""),
        provider_id=provider.id if provider else None,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    # 手动构建返回对象，避免触发异步懒加载
    out = ChatSessionOut.model_validate(session)
    out.message_count = 0
    detail = ChatSessionDetail(**out.model_dump())
    detail.messages = []
    return detail


@router.get("/{session_id}", response_model=ChatSessionDetail)
async def get_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取会话详情（含消息列表）"""
    result = await db.execute(
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
    )
    session = result.scalars().first()
    if not session:
        raise HTTPException(404, "会话不存在")
    detail = ChatSessionDetail.model_validate(session)
    detail.message_count = len(session.messages)
    return detail


@router.put("/{session_id}", response_model=ChatSessionOut)
async def update_session(
    session_id: int,
    body: ChatSessionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新会话（重命名、切换模型等）"""
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
    )
    session = result.scalars().first()
    if not session:
        raise HTTPException(404, "会话不存在")

    if body.title is not None:
        session.title = body.title
    if "keyword_id" in body.model_fields_set:
        session.keyword_id = body.keyword_id
    if body.model is not None:
        session.model = body.model
        # 同步更新 provider_id
        provider = await get_current_provider(db, current_user.id)
        if provider:
            session.provider_id = provider.id

    await db.commit()
    await db.refresh(session)
    out = ChatSessionOut.model_validate(session)
    return out


@router.delete("/{session_id}")
async def delete_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除会话 — 消息和记忆随会话级联删除"""
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
    )
    session = result.scalars().first()
    if not session:
        raise HTTPException(404, "会话不存在")

    await db.delete(session)
    await db.commit()
    return {"ok": True}


@router.post("/{session_id}/messages")
async def send_message(
    session_id: int,
    body: SessionChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """在会话中发送消息 — 带记忆和上下文压缩"""
    result = await db.execute(
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
    )
    session = result.scalars().first()
    if not session:
        raise HTTPException(404, "会话不存在")

    # 保存用户消息
    user_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=body.message,
        token_count=len(body.message) // 4,
    )
    db.add(user_msg)
    await db.flush()

    # 权限 + Token 限额检查
    provider = await get_current_provider(db, session.user_id)
    if provider and not is_admin(current_user):
        has_access = await check_provider_access(db, current_user, provider.id)
        if not has_access:
            raise HTTPException(403, "暂无权限使用此智能体，请联系管理员")
    allowed, quota_msg = await check_token_quota(db, current_user)
    if not allowed:
        raise HTTPException(429, quota_msg)

    # 调用 AI（带记忆和上下文）
    result_data = await chat_with_session(db, session, body.message, body.model)

    if "error" not in result_data:
        # 记录 Token 用量
        prompt_tokens = estimate_tokens(body.message)
        completion_tokens = estimate_tokens(result_data.get("reply", ""))
        await log_token_usage(
            db, current_user.id,
            result_data.get("provider_id"),
            "chat",
            prompt_tokens, completion_tokens,
        )
        # 保存 AI 回复
        ai_reply = result_data.get("reply", "")
        ai_msg = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=ai_reply,
            token_count=len(ai_reply) // 4,
        )
        db.add(ai_msg)

        # 如果触发了上下文压缩，更新记忆
        if result_data.get("compressed"):
            session.memory_summary = result_data.get("memory_summary", "")
            session.context_compressed = True

        # 自动生成标题（首次对话）
        if session.title == "新对话" and len(session.messages) <= 1:
            title = body.message[:30].strip()
            if len(body.message) > 30:
                title += "..."
            session.title = title

        await db.commit()
    else:
        await db.rollback()

    return result_data


@router.post("/{session_id}/compress")
async def manual_compress(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动触发上下文压缩"""
    result = await db.execute(
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
    )
    session = result.scalars().first()
    if not session:
        raise HTTPException(404, "会话不存在")

    summary = await compress_session_context(db, session)
    session.memory_summary = summary
    session.context_compressed = True
    await db.commit()
    return {"ok": True, "memory_summary": summary}

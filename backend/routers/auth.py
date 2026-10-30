"""Registration, login, session inspection, and logout routes."""
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import DEFAULT_DATA_SOURCES
from database import get_db
from models import AuthSession, DataSource, User
from schemas import AuthResponse, LoginRequest, RegisterRequest, UserOut
from services.auth_service import (
    bearer_scheme,
    create_session,
    get_current_user,
    hash_password,
    token_digest,
    verify_password,
)
from services.email_service import is_email_enabled, verify_code

router = APIRouter(prefix="/api/auth", tags=["用户认证"])


def _normalize_username(value: str) -> str:
    username = value.strip().lower()
    if not re.fullmatch(r"[^\s/\\]{3,50}", username):
        raise HTTPException(422, "用户名需为 3-50 个字符，且不能包含空格或斜杠")
    return username


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    username = _normalize_username(data.username)
    existing = await db.execute(
        select(User.id).where(func.lower(User.username) == username)
    )
    if existing.scalar():
        raise HTTPException(409, "用户名已存在")

    # 邮箱验证
    email = data.email.strip().lower() if data.email else ""
    if email:
        if "@" not in email or "." not in email:
            raise HTTPException(422, "邮箱格式不正确")
        email_exists = await db.execute(select(User).where(User.email == email))
        existing_email_user = email_exists.scalars().first()
        if existing_email_user:
            if existing_email_user.email_verified:
                raise HTTPException(409, "该邮箱已注册，请直接登录或更换邮箱")
            # 邮箱未验证 → 释放旧邮箱，允许新用户注册
            existing_email_user.email = ""
            await db.flush()
        # 如果邮件服务启用，验证码必填
        if is_email_enabled():
            if not data.verification_code:
                raise HTTPException(422, "请输入邮箱验证码")
            if not verify_code(email, data.verification_code):
                raise HTTPException(400, "验证码错误或已过期")

    user = User(
        username=username,
        password_hash=hash_password(data.password),
        display_name=data.display_name.strip() or username,
        email=email,
        email_verified=bool(email and is_email_enabled()),
    )
    db.add(user)
    await db.flush()
    db.add_all(DataSource(user_id=user.id, **source) for source in DEFAULT_DATA_SOURCES)
    await db.commit()
    await db.refresh(user)
    token, expires_at = await create_session(db, user)
    return AuthResponse(access_token=token, expires_at=expires_at, user=user)


@router.post("/login", response_model=AuthResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    username = data.username.strip().lower()
    user = (
        await db.execute(select(User).where(func.lower(User.username) == username))
    ).scalars().first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    if not user.is_active:
        raise HTTPException(403, "账号已停用")
    token, expires_at = await create_session(db, user)
    return AuthResponse(access_token=token, expires_at=expires_at, user=user)


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if credentials:
        session = (
            await db.execute(
                select(AuthSession).where(
                    AuthSession.user_id == current_user.id,
                    AuthSession.token_hash == token_digest(credentials.credentials),
                )
            )
        ).scalars().first()
        if session:
            await db.delete(session)
            await db.commit()
    return {"message": "已退出登录"}

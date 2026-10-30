"""用户资料管理路由 — 个人信息、头像、密码修改"""
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import UPLOAD_DIR
from database import get_db
from models import User
from schemas import ChangePasswordRequest, SendCodeRequest, UpdateProfileRequest, UserOut
from services.auth_service import get_current_user, hash_password, verify_password
from services.email_service import is_email_enabled, send_verification_code, verify_code

router = APIRouter(prefix="/api/profile", tags=["用户资料"])

AVATAR_DIR = UPLOAD_DIR / "avatars"
AVATAR_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_AVATAR_SIZE = 5 * 1024 * 1024  # 5MB


@router.get("", response_model=UserOut)
async def get_profile(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("", response_model=UserOut)
async def update_profile(
    body: UpdateProfileRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新个人信息"""
    if body.display_name is not None:
        current_user.display_name = body.display_name.strip()
    if body.email is not None:
        new_email = body.email.strip()
        if new_email and new_email != current_user.email:
            # 检查邮箱是否已被使用
            existing = await db.execute(
                select(User.id).where(User.email == new_email, User.id != current_user.id)
            )
            if existing.scalar():
                raise HTTPException(409, "该邮箱已被其他账号使用")
            # 邮件启用时，必须验证码验证
            if is_email_enabled():
                if not body.email_verification_code:
                    raise HTTPException(422, "更换邮箱需要输入验证码")
                if not verify_code(new_email, body.email_verification_code):
                    raise HTTPException(400, "验证码错误或已过期")
                current_user.email_verified = True
            else:
                current_user.email_verified = False
            current_user.email = new_email
        elif new_email and new_email == current_user.email and not current_user.email_verified:
            # 邮箱未变更但未验证 → 验证当前邮箱
            if is_email_enabled() and body.email_verification_code:
                if not verify_code(new_email, body.email_verification_code):
                    raise HTTPException(400, "验证码错误或已过期")
                current_user.email_verified = True
    if body.phone is not None:
        current_user.phone = body.phone.strip()
    if body.notify_on_crawl is not None:
        current_user.notify_on_crawl = body.notify_on_crawl
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post("/avatar", response_model=UserOut)
async def upload_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传用户头像"""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(422, "仅支持 JPG/PNG/WebP/GIF 格式")
    contents = await file.read()
    if len(contents) > MAX_AVATAR_SIZE:
        raise HTTPException(422, "头像文件不能超过 5MB")

    # 删除旧头像文件
    if current_user.avatar:
        old_path = UPLOAD_DIR / current_user.avatar.replace("/uploads/", "")
        if old_path.exists():
            old_path.unlink()

    ext = file.content_type.split("/")[-1]
    if ext == "jpeg":
        ext = "jpg"
    filename = f"avatars/{current_user.id}_{uuid.uuid4().hex[:8]}.{ext}"
    filepath = UPLOAD_DIR / filename.replace("avatars/", "avatars/")
    filepath.write_bytes(contents)

    current_user.avatar = f"/uploads/{filename}"
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """修改密码"""
    if not verify_password(body.old_password, current_user.password_hash):
        raise HTTPException(400, "原密码错误")
    current_user.password_hash = hash_password(body.new_password)
    await db.commit()
    return {"ok": True, "message": "密码修改成功"}


@router.post("/send-code")
async def send_code(
    body: SendCodeRequest,
    db: AsyncSession = Depends(get_db),
):
    """发送邮箱验证码（注册用 / 换绑邮箱用）"""
    email = body.email.strip().lower()
    if not "@" in email or "." not in email:
        raise HTTPException(422, "邮箱格式不正确")

    # 检查邮箱是否已被其他用户注册
    existing = await db.execute(
        select(User).where(User.email == email)
    )
    existing_user = existing.scalars().first()
    if existing_user:
        # 邮箱已注册且已验证 → 不允许重发
        if existing_user.email_verified:
            raise HTTPException(409, "该邮箱已注册，请直接登录或更换邮箱")
        # 邮箱已注册但未验证 → 允许重发验证码（用户可能上次没收到）

    if not is_email_enabled():
        return {
            "success": False,
            "message": "邮件服务未启用。请在 config.py 的 SMTP_CONFIG 中配置 SMTP 并设 enabled=True。"
                       " 配置前可使用任意 6 位数字作为验证码测试。",
            "dev_mode": True,
        }
    result = send_verification_code(email)
    if not result["success"]:
        raise HTTPException(500, result["message"])
    return result


@router.post("/send-change-email-code")
async def send_change_email_code(
    body: SendCodeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """已登录用户修改邮箱时发送验证码"""
    email = body.email.strip().lower()
    if not "@" in email or "." not in email:
        raise HTTPException(422, "邮箱格式不正确")
    if email == current_user.email.strip().lower() and current_user.email_verified:
        raise HTTPException(422, "新邮箱与当前邮箱相同且已验证")

    # 检查邮箱是否已被其他用户使用
    existing = await db.execute(
        select(User.id).where(User.email == email, User.id != current_user.id)
    )
    if existing.scalar():
        raise HTTPException(409, "该邮箱已被其他账号使用")

    if not is_email_enabled():
        raise HTTPException(503, "邮件服务未启用，请在 config.py 中配置 SMTP")
    result = send_verification_code(email)
    if not result["success"]:
        raise HTTPException(500, result["message"])
    return result


@router.post("/verify-code")
async def verify_email_code(body: dict):
    """验证邮箱验证码"""
    email = body.get("email", "").strip().lower()
    code = body.get("code", "").strip()
    if not email or not code:
        raise HTTPException(422, "邮箱和验证码不能为空")
    if verify_code(email, code):
        return {"success": True, "message": "验证码正确"}
    raise HTTPException(400, "验证码错误或已过期")

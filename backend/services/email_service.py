"""邮件服务 — 注册验证码 + 采集成功通知

配置方式：
  在 backend/config.py 的 SMTP_CONFIG 中填写你的 SMTP 信息：
    - host: SMTP 服务器地址 (如 smtp.qq.com, smtp.163.com, smtp.gmail.com)
    - port: 端口 (SSL: 465, TLS: 587)
    - username: 发件邮箱地址
    - password: SMTP 授权码 (QQ邮箱→设置→账户→SMTP授权码)
    - enabled: 改为 True 启用

常见邮箱配置：
  QQ邮箱:      host=smtp.qq.com,  port=465, use_ssl=True
  163邮箱:     host=smtp.163.com, port=465, use_ssl=True
  Gmail:       host=smtp.gmail.com, port=587, use_ssl=False (需应用专用密码)
  企业微信邮箱: host=smtp.exmail.qq.com, port=465, use_ssl=True
  Outlook:    host=smtp-mail.outlook.com, port=587, use_ssl=False
"""
import random
import smtplib
import string
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr

from config import SMTP_CONFIG, VERIFY_CODE_EXPIRE_MINUTES

# 内存验证码存储: {email: (code, expire_time)}
_verify_codes: dict[str, tuple[str, datetime]] = {}


def is_email_enabled() -> bool:
    return bool(SMTP_CONFIG.get("enabled") and SMTP_CONFIG.get("host") and SMTP_CONFIG.get("username"))


def generate_code(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


def send_email(to_address: str, subject: str, html_body: str) -> bool:
    """发送邮件。成功返回 True，失败返回 False。"""
    if not is_email_enabled():
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = formataddr((str(Header(SMTP_CONFIG['sender_name'], 'utf-8')), SMTP_CONFIG['username']))
        msg["To"] = to_address
        msg["Subject"] = Header(subject, 'utf-8')
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        if SMTP_CONFIG.get("use_ssl", True):
            server = smtplib.SMTP_SSL(SMTP_CONFIG["host"], SMTP_CONFIG["port"], timeout=30)
        else:
            server = smtplib.SMTP(SMTP_CONFIG["host"], SMTP_CONFIG["port"], timeout=30)
            server.starttls()
        server.login(SMTP_CONFIG["username"], SMTP_CONFIG["password"])
        server.sendmail(SMTP_CONFIG["username"], [to_address], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"[EmailService] 发送失败: {e}")
        return False


def send_verification_code(email: str) -> dict:
    """发送注册验证码"""
    if not is_email_enabled():
        return {
            "success": False,
            "message": "邮件服务未启用。请在 config.py 中配置 SMTP 信息后启用。",
        }
    code = generate_code()
    expire_at = datetime.now() + timedelta(minutes=VERIFY_CODE_EXPIRE_MINUTES)
    _verify_codes[email] = (code, expire_at)

    html = f"""
    <div style="max-width:480px;margin:0 auto;font-family:'Microsoft YaHei',sans-serif;">
      <div style="background:#409eff;color:#fff;padding:20px 24px;border-radius:8px 8px 0 0;">
        <h2 style="margin:0;font-size:18px;">策知 · 注册验证码</h2>
      </div>
      <div style="padding:24px;border:1px solid #e8e8e8;border-top:none;border-radius:0 0 8px 8px;">
        <p style="color:#333;font-size:14px;">您好，您的注册验证码为：</p>
        <div style="text-align:center;margin:16px 0;">
          <span style="font-size:28px;font-weight:bold;color:#409eff;letter-spacing:4px;">{code}</span>
        </div>
        <p style="color:#999;font-size:12px;">验证码 {VERIFY_CODE_EXPIRE_MINUTES} 分钟内有效，请尽快使用。</p>
        <p style="color:#999;font-size:12px;">如非本人操作，请忽略此邮件。</p>
      </div>
    </div>
    """
    success = send_email(email, "策知 · 注册验证码", html)
    if success:
        return {"success": True, "message": f"验证码已发送至 {email}"}
    return {"success": False, "message": "验证码发送失败，请检查邮箱地址或稍后重试"}


def verify_code(email: str, code: str) -> bool:
    """验证注册验证码"""
    stored = _verify_codes.get(email)
    if not stored:
        return False
    stored_code, expire_at = stored
    if datetime.now() > expire_at:
        del _verify_codes[email]
        return False
    if stored_code != code:
        return False
    del _verify_codes[email]
    return True


async def send_crawl_notification(email: str, keyword: str, new_count: int, total_count: int) -> bool:
    """采集任务成功后发送邮件通知"""
    if not is_email_enabled() or not email:
        return False
    html = f"""
    <div style="max-width:480px;margin:0 auto;font-family:'Microsoft YaHei',sans-serif;">
      <div style="background:#67c23a;color:#fff;padding:20px 24px;border-radius:8px 8px 0 0;">
        <h2 style="margin:0;font-size:18px;">策知 · 采集完成通知</h2>
      </div>
      <div style="padding:24px;border:1px solid #e8e8e8;border-top:none;border-radius:0 0 8px 8px;">
        <p style="color:#333;font-size:14px;">您好，您的采集任务已完成：</p>
        <table style="width:100%;font-size:14px;margin:12px 0;">
          <tr><td style="color:#999;padding:4px 0;">关键词</td><td style="color:#333;font-weight:600;">{keyword}</td></tr>
          <tr><td style="color:#999;padding:4px 0;">新增文章</td><td style="color:#67c23a;font-weight:600;">{new_count} 篇</td></tr>
          <tr><td style="color:#999;padding:4px 0;">累计文章</td><td style="color:#333;font-weight:600;">{total_count} 篇</td></tr>
        </table>
        <p style="color:#999;font-size:12px;">请登录策知平台查看最新采集内容。</p>
      </div>
    </div>
    """
    return send_email(email, f"策知 · 「{keyword}」采集完成通知", html)

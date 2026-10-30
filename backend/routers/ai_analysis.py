"""AI 分析路由"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import AIProvider, AnalysisResult, ChatMessage, ChatSession, User
from schemas import AnalysisRequest, AnalysisResultOut, ChatRequest
from services.ai_service import (
    chat_with_context,
    generate_summary,
)
from services.local_analysis import (
    generate_local_chart_data,
    generate_local_wordcloud,
)
from services.auth_service import get_current_user
from services.permission_service import (
    check_provider_access,
    check_token_quota,
    estimate_tokens,
    is_admin,
    log_token_usage,
)

router = APIRouter(prefix="/api/analysis", tags=["AI 分析"])


async def _check_ai_permission(db: AsyncSession, user: User, provider_id: int | None):
    """检查用户是否有权使用当前 Provider + Token 限额"""
    if provider_id:
        has_access = await check_provider_access(db, user, provider_id)
        if not has_access:
            raise HTTPException(403, "暂无权限使用此智能体，请联系管理员")
    allowed, msg = await check_token_quota(db, user)
    if not allowed:
        raise HTTPException(429, msg)


@router.post("/summary")
async def api_summary(
    request: AnalysisRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 获取当前 Provider 并检查权限
    from services.ai_service import get_current_provider
    provider = await get_current_provider(db, current_user.id)
    if provider:
        await _check_ai_permission(db, current_user, provider.id)

    result = await generate_summary(
        db, current_user.id, request.article_ids, request.keyword_id, request.model
    )
    if "error" not in result:
        # 记录 Token 用量
        prompt_tokens = estimate_tokens(request.article_ids and str(request.article_ids) or "")
        completion_tokens = estimate_tokens(result.get("summary", ""))
        await log_token_usage(
            db, current_user.id,
            result.get("provider_id"),
            "summary",
            prompt_tokens, completion_tokens,
        )
        record = AnalysisResult(
            user_id=current_user.id,
            analysis_type="summary",
            keyword_id=request.keyword_id,
            model=result.get("model", ""),
            provider_id=result.get("provider_id"),
            result=result,
        )
        db.add(record)
        await db.commit()
    return result


@router.post("/wordcloud")
async def api_wordcloud(
    request: AnalysisRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """本地词云分析 — 使用 jieba 分词，不调用 AI"""
    result = await generate_local_wordcloud(
        db, current_user.id, request.article_ids, request.keyword_id
    )
    if "error" not in result:
        record = AnalysisResult(
            user_id=current_user.id,
            analysis_type="wordcloud",
            keyword_id=request.keyword_id,
            model="local",
            provider_id=None,
            result=result,
        )
        db.add(record)
        await db.commit()
    return result


@router.post("/chart")
async def api_chart(
    request: AnalysisRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """本地图表分析 — 统计分析，不调用 AI"""
    result = await generate_local_chart_data(
        db, current_user.id, request.article_ids, request.keyword_id
    )
    if "error" not in result:
        record = AnalysisResult(
            user_id=current_user.id,
            analysis_type="chart",
            keyword_id=request.keyword_id,
            model="local",
            provider_id=None,
            result=result,
        )
        db.add(record)
        await db.commit()
    return result


@router.post("/chat")
async def api_chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 权限 + 限额检查
    from services.ai_service import get_current_provider
    provider = await get_current_provider(db, current_user.id)
    if provider:
        await _check_ai_permission(db, current_user, provider.id)

    result = await chat_with_context(
        db,
        current_user.id,
        request.message,
        request.article_ids,
        request.keyword_id,
        request.model,
    )
    if "error" not in result:
        # 记录 Token 用量
        prompt_tokens = estimate_tokens(request.message)
        completion_tokens = estimate_tokens(result.get("reply", ""))
        await log_token_usage(
            db, current_user.id,
            result.get("provider_id"),
            "chat",
            prompt_tokens, completion_tokens,
        )
        record = AnalysisResult(
            user_id=current_user.id,
            analysis_type="chat",
            keyword_id=request.keyword_id,
            model=result.get("model", ""),
            provider_id=result.get("provider_id"),
            prompt=request.message,
            result=result,
        )
        db.add(record)
        await db.commit()
    return result


@router.get("/history", response_model=list[AnalysisResultOut])
async def get_history(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AnalysisResult)
        .where(AnalysisResult.user_id == current_user.id)
        .order_by(AnalysisResult.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/summary/{result_id}/download")
async def download_summary(
    result_id: int,
    format: str = "md",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """下载摘要分析结果 — 支持 .md 和 .docx 格式"""
    result = await db.execute(
        select(AnalysisResult).where(
            AnalysisResult.id == result_id,
            AnalysisResult.user_id == current_user.id,
        )
    )
    record = result.scalars().first()
    if not record:
        return {"error": "未找到分析记录"}

    summary_text = record.result.get("summary", "")
    if not summary_text:
        return {"error": "该记录无摘要内容"}

    title = f"策知 · 摘要分析报告"
    model_info = f"模型: {record.model}"

    if format == "docx":
        # 生成简单的 docx 格式（实际上是 HTML 内容以 .doc 扩展名）
        html_content = f"""<html xmlns:o="urn:schemas-microsoft-com:office:office"
xmlns:w="urn:schemas-microsoft-com:office:word"
xmlns="http://www.w3.org/TR/REC-html40">
<head><meta charset="utf-8"><title>{title}</title></head>
<body style="font-family: 'Microsoft YaHei', sans-serif; font-size: 14px; line-height: 1.8;">
<h1>{title}</h1>
<p style="color: #999; font-size: 12px;">{model_info} · 生成时间: {record.created_at.strftime('%Y-%m-%d %H:%M')}</p>
<hr/>
<div>{summary_text.replace(chr(10), '<br/>')}</div>
</body>
</html>"""
        from fastapi.responses import Response
        return Response(
            content=html_content.encode("utf-8"),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename=summary_{result_id}.doc"},
        )
    else:
        # Markdown 格式
        md_content = f"# {title}\n\n> {model_info} · 生成时间: {record.created_at.strftime('%Y-%m-%d %H:%M')}\n\n---\n\n{summary_text}\n"
        return PlainTextResponse(
            content=md_content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=summary_{result_id}.md"},
        )


# ========== 用量统计 ==========

@router.get("/usage-stats")
async def get_usage_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """AI 用量统计 — 聚合分析记录与对话数据"""

    # ---- 1. 分析结果按类型统计 ----
    type_rows = await db.execute(
        select(AnalysisResult.analysis_type, func.count(AnalysisResult.id))
        .where(AnalysisResult.user_id == current_user.id)
        .group_by(AnalysisResult.analysis_type)
    )
    by_type = {row[0]: row[1] for row in type_rows}
    total_analysis = sum(by_type.values())

    # ---- 2. 分析结果按模型统计 ----
    model_rows = await db.execute(
        select(AnalysisResult.model, func.count(AnalysisResult.id))
        .where(AnalysisResult.user_id == current_user.id, AnalysisResult.model != "")
        .group_by(AnalysisResult.model)
        .order_by(func.count(AnalysisResult.id).desc())
    )
    by_model = [
        {"model": row[0], "count": row[1]} for row in model_rows
    ]

    # ---- 3. 分析结果按提供商统计 ----
    provider_rows = await db.execute(
        select(AnalysisResult.provider_id, func.count(AnalysisResult.id))
        .where(AnalysisResult.user_id == current_user.id, AnalysisResult.provider_id.isnot(None))
        .group_by(AnalysisResult.provider_id)
    )
    provider_id_counts = {row[0]: row[1] for row in provider_rows}

    # 查提供商名称
    providers_map = {}
    if provider_id_counts:
        prov_result = await db.execute(
            select(AIProvider.id, AIProvider.name)
            .where(AIProvider.id.in_(list(provider_id_counts.keys())))
        )
        providers_map = {row[0]: row[1] for row in prov_result}

    by_provider = [
        {"provider_id": pid, "name": providers_map.get(pid, f"ID:{pid}"), "count": cnt}
        for pid, cnt in sorted(provider_id_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    # ---- 4. 对话统计 ----
    session_count_row = await db.execute(
        select(func.count(ChatSession.id))
        .where(ChatSession.user_id == current_user.id, ChatSession.is_active == True)
    )
    total_sessions = session_count_row.scalar() or 0

    # 对话消息统计（需要关联 session 获取 user_id）
    msg_rows = await db.execute(
        select(ChatMessage.role, func.count(ChatMessage.id), func.coalesce(func.sum(ChatMessage.token_count), 0))
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.user_id == current_user.id)
        .group_by(ChatMessage.role)
    )
    chat_msg_stats = {}
    total_chat_tokens = 0
    for role, cnt, tokens in msg_rows:
        chat_msg_stats[role] = {"count": cnt, "tokens": tokens}
        total_chat_tokens += tokens

    total_chat_messages = sum(s["count"] for s in chat_msg_stats.values())

    # ---- 5. 近 7 天每日趋势 ----
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    daily_labels = []
    daily_analysis = []
    daily_chat = []
    for i in range(6, -1, -1):
        day_start = today - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        daily_labels.append(day_start.strftime("%m-%d"))

        # 当日分析数
        a_count_row = await db.execute(
            select(func.count(AnalysisResult.id))
            .where(
                AnalysisResult.user_id == current_user.id,
                AnalysisResult.created_at >= day_start,
                AnalysisResult.created_at < day_end,
            )
        )
        daily_analysis.append(a_count_row.scalar() or 0)

        # 当日对话消息数
        c_count_row = await db.execute(
            select(func.count(ChatMessage.id))
            .join(ChatSession, ChatMessage.session_id == ChatSession.id)
            .where(
                ChatSession.user_id == current_user.id,
                ChatMessage.created_at >= day_start,
                ChatMessage.created_at < day_end,
            )
        )
        daily_chat.append(c_count_row.scalar() or 0)

    # ---- 6. 估算总 token ----
    # 分析结果：用 prompt 长度 + 粗略估算 result 内容
    prompt_len_row = await db.execute(
        select(func.coalesce(func.sum(func.length(AnalysisResult.prompt)), 0))
        .where(AnalysisResult.user_id == current_user.id)
    )
    prompt_total_chars = prompt_len_row.scalar() or 0
    # 粗略估算：每次分析平均输出 ~800 字符，加上 prompt
    analysis_tokens = (prompt_total_chars + total_analysis * 800) // 4

    total_tokens = analysis_tokens + total_chat_tokens

    return {
        "total_analysis": total_analysis,
        "by_type": {
            "summary": by_type.get("summary", 0),
            "chat": by_type.get("chat", 0),
            "chart": by_type.get("chart", 0),
            "wordcloud": by_type.get("wordcloud", 0),
        },
        "by_model": by_model,
        "by_provider": by_provider,
        "total_sessions": total_sessions,
        "total_chat_messages": total_chat_messages,
        "chat_messages_by_role": chat_msg_stats,
        "total_tokens": total_tokens,
        "analysis_tokens": analysis_tokens,
        "chat_tokens": total_chat_tokens,
        "daily": {
            "labels": daily_labels,
            "analysis": daily_analysis,
            "chat": daily_chat,
        },
    }

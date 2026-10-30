"""Crawler job routes."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import CrawlItem, CrawlLog, User
from schemas import CrawlItemOut, CrawlLogOut, CrawlRequest
from services.crawler_service import create_crawl_logs, execute_crawl_logs
from services.auth_service import get_current_user

router = APIRouter(prefix="/api/crawler", tags=["采集"])


def _log_out(log: CrawlLog) -> CrawlLogOut:
    duration = None
    if log.finished_at and log.started_at:
        duration = max(0, (log.finished_at - log.started_at).total_seconds())
    return CrawlLogOut.model_validate({**log.__dict__, "duration": duration})


@router.post("/run")
async def run_crawl(
    request: CrawlRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create durable pending jobs, then execute them in the local background."""
    log_ids, skipped = await create_crawl_logs(
        db,
        keyword_ids=request.keyword_ids,
        source_ids=request.source_ids,
        force=request.force,
        user_id=current_user.id,
    )
    if log_ids:
        background_tasks.add_task(execute_crawl_logs, log_ids, request.source_ids)
    return {
        "message": f"已创建 {len(log_ids)} 个采集任务",
        "status": "pending" if log_ids else "skipped",
        "log_ids": log_ids,
        "skipped_keyword_ids": skipped,
    }


@router.get("/logs", response_model=list[CrawlLogOut])
async def get_crawl_logs(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    logs = (
        await db.execute(
            select(CrawlLog)
            .where(CrawlLog.user_id == current_user.id)
            .order_by(CrawlLog.started_at.desc(), CrawlLog.id.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [_log_out(log) for log in logs]


@router.get("/logs/{log_id}", response_model=CrawlLogOut)
async def get_crawl_log(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    log = (
        await db.execute(
            select(CrawlLog).where(
                CrawlLog.id == log_id, CrawlLog.user_id == current_user.id
            )
        )
    ).scalars().first()
    if not log:
        raise HTTPException(404, "采集任务不存在")
    return _log_out(log)


@router.get("/logs/{log_id}/items", response_model=list[CrawlItemOut])
async def get_crawl_items(
    log_id: int,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exists = (
        await db.execute(
            select(CrawlLog).where(
                CrawlLog.id == log_id, CrawlLog.user_id == current_user.id
            )
        )
    ).scalars().first()
    if not exists:
        raise HTTPException(404, "采集任务不存在")
    result = await db.execute(
        select(CrawlItem)
        .where(CrawlItem.crawl_log_id == log_id)
        .order_by(CrawlItem.id)
        .limit(limit)
    )
    return result.scalars().all()


@router.delete("/logs/{log_id}")
async def delete_crawl_log(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除采集任务记录及其明细"""
    log = (
        await db.execute(
            select(CrawlLog).where(
                CrawlLog.id == log_id, CrawlLog.user_id == current_user.id
            )
        )
    ).scalars().first()
    if not log:
        raise HTTPException(404, "采集任务不存在")
    await db.execute(delete(CrawlItem).where(CrawlItem.crawl_log_id == log_id))
    await db.delete(log)
    await db.commit()
    return {"message": "已删除"}

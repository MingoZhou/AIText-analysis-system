"""Local APScheduler process for interval-aware keyword collection."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from config import SCHEDULER_CHECK_MINUTES, SCHEDULER_ENABLED
from database import async_session
from models import Keyword
from services.crawler_service import create_crawl_logs, execute_crawl_logs

scheduler = AsyncIOScheduler(timezone=ZoneInfo("Asia/Shanghai"))


async def _scheduled_crawl():
    """Queue only active keyword strategies whose own interval is due."""
    async with async_session() as db:
        keywords = (
            await db.execute(select(Keyword).where(Keyword.is_active == True))
        ).scalars().all()
        now = datetime.now()
        due_ids = [
            keyword.id
            for keyword in keywords
            if keyword.last_crawl_at is None
            or now - keyword.last_crawl_at >= timedelta(hours=keyword.crawl_interval)
        ]
        if not due_ids:
            return
        log_ids, _ = await create_crawl_logs(db, keyword_ids=due_ids)
    if log_ids:
        await execute_crawl_logs(log_ids)


def start_scheduler():
    if not SCHEDULER_ENABLED or scheduler.running:
        return
    scheduler.add_job(
        _scheduled_crawl,
        IntervalTrigger(minutes=SCHEDULER_CHECK_MINUTES),
        id="keyword-crawl-check",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    scheduler.start()
    print(f"[Scheduler] 每 {SCHEDULER_CHECK_MINUTES} 分钟检查一次关键词采集间隔")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)

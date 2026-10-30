"""首页看板路由"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import AIProvider, Article, ArticleKeyword, Keyword, User
from schemas import ArticleOut, DashboardStats
from routers.articles import _keyword_map, _to_out
from services.auth_service import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["看板"])


@router.get("/stats", response_model=DashboardStats)
async def get_stats(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    # 关键词数
    kw_count = (
        await db.execute(
            select(func.count(Keyword.id)).where(Keyword.user_id == current_user.id)
        )
    ).scalar() or 0
    # 文章数
    art_count = (
        await db.execute(
            select(func.count(Article.id)).where(Article.user_id == current_user.id)
        )
    ).scalar() or 0
    # 未读
    unread = (
        await db.execute(
            select(func.count(Article.id)).where(
                Article.user_id == current_user.id, Article.is_read == False
            )
        )
    ).scalar() or 0
    # 收藏
    starred = (
        await db.execute(
            select(func.count(Article.id)).where(
                Article.user_id == current_user.id, Article.is_starred == True
            )
        )
    ).scalar() or 0
    # PDF
    pdf_count = (
        await db.execute(
            select(func.count(Article.id)).where(
                Article.user_id == current_user.id, Article.file_type == "pdf"
            )
        )
    ).scalar() or 0
    # 提供商
    provider_count = (
        await db.execute(
            select(func.count(AIProvider.id)).where(
                AIProvider.user_id == current_user.id, AIProvider.is_active == True
            )
        )
    ).scalar() or 0
    # 今日采集
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = (
        await db.execute(
            select(func.count(Article.id)).where(
                Article.user_id == current_user.id, Article.crawl_date >= today_start
            )
        )
    ).scalar() or 0

    # 最近 5 篇
    recent_articles_raw = (
        await db.execute(
            select(Article)
            .where(Article.user_id == current_user.id)
            .order_by(Article.crawl_date.desc())
            .limit(5)
        )
    ).scalars().all()
    recent_keyword_map = await _keyword_map(
        db, [article.id for article in recent_articles_raw], current_user.id
    )
    recent_articles = [
        _to_out(article, recent_keyword_map.get(article.id))
        for article in recent_articles_raw
    ]

    # 类型分布
    type_result = await db.execute(
        select(Article.source_type, func.count(Article.id))
        .where(Article.user_id == current_user.id)
        .group_by(Article.source_type)
    )
    type_distribution = {row[0]: row[1] for row in type_result.all()}

    # 近 7 天趋势
    trend_data = []
    for i in range(6, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        day_start = datetime.strptime(day, "%Y-%m-%d")
        day_end = day_start + timedelta(days=1)
        count = (
            await db.execute(
                select(func.count(Article.id)).where(
                    Article.user_id == current_user.id,
                    Article.crawl_date >= day_start,
                    Article.crawl_date < day_end,
                )
            )
        ).scalar() or 0
        trend_data.append({"date": day, "count": count})

    # 关键词分布
    kw_dist_result = await db.execute(
        select(Keyword.keyword, func.count(ArticleKeyword.article_id))
        .join(ArticleKeyword, ArticleKeyword.keyword_id == Keyword.id, isouter=True)
        .where(Keyword.user_id == current_user.id)
        .group_by(Keyword.id, Keyword.keyword)
        .order_by(func.count(ArticleKeyword.article_id).desc())
        .limit(10)
    )
    keyword_distribution = [{"name": row[0], "value": row[1]} for row in kw_dist_result.all()]

    return DashboardStats(
        keyword_count=kw_count,
        article_count=art_count,
        unread_count=unread,
        starred_count=starred,
        pdf_count=pdf_count,
        provider_count=provider_count,
        today_count=today_count,
        recent_articles=recent_articles,
        type_distribution=type_distribution,
        trend_data=trend_data,
        keyword_distribution=keyword_distribution,
    )

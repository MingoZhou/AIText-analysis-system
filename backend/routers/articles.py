"""Normalized document library routes."""
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import AnalysisResult, Article, ArticleKeyword, CrawlItem, Keyword, User
from schemas import ArticleListOut, ArticleOut
from services.auth_service import get_current_user

router = APIRouter(prefix="/api/articles", tags=["文献库"])


def _to_out(art: Article, keyword_rows: list[tuple[int, str]] | None = None) -> ArticleOut:
    keyword_rows = keyword_rows or []
    keyword_ids = [row[0] for row in keyword_rows]
    keyword_texts = [row[1] for row in keyword_rows]
    return ArticleOut.model_validate({
        **art.__dict__,
        "keyword_text": "、".join(keyword_texts),
        "keyword_ids": keyword_ids,
        "keyword_texts": keyword_texts,
    })


async def _keyword_map(
    db: AsyncSession, article_ids: list[int], user_id: int
) -> dict[int, list[tuple[int, str]]]:
    if not article_ids:
        return {}
    rows = (
        await db.execute(
            select(ArticleKeyword.article_id, Keyword.id, Keyword.keyword)
            .join(Keyword, Keyword.id == ArticleKeyword.keyword_id)
            .join(Article, Article.id == ArticleKeyword.article_id)
            .where(
                ArticleKeyword.article_id.in_(article_ids),
                Article.user_id == user_id,
                Keyword.user_id == user_id,
            )
            .order_by(ArticleKeyword.article_id, Keyword.id)
        )
    ).all()
    output: dict[int, list[tuple[int, str]]] = {}
    for article_id, keyword_id, keyword_text in rows:
        output.setdefault(article_id, []).append((keyword_id, keyword_text))
    return output


@router.get("", response_model=ArticleListOut)
async def list_articles(
    keyword_id: int | None = None,
    source_type: str | None = None,
    search: str | None = None,
    is_starred: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filters = [Article.user_id == current_user.id]
    if source_type:
        filters.append(Article.source_type == source_type)
    if search:
        filters.append(
            Article.title.contains(search) | Article.content.contains(search)
        )
    if is_starred is not None:
        filters.append(Article.is_starred == is_starred)

    query = select(Article)
    count_query = select(func.count(func.distinct(Article.id))).select_from(Article)
    if keyword_id:
        query = query.join(ArticleKeyword).where(ArticleKeyword.keyword_id == keyword_id)
        count_query = count_query.join(ArticleKeyword).where(
            ArticleKeyword.keyword_id == keyword_id
        )
    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)

    total = (await db.execute(count_query)).scalar() or 0
    articles = (
        await db.execute(
            query.order_by(Article.crawl_date.desc(), Article.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().unique().all()
    keyword_map = await _keyword_map(
        db, [article.id for article in articles], current_user.id
    )
    return ArticleListOut(
        total=total,
        items=[_to_out(article, keyword_map.get(article.id)) for article in articles],
    )


@router.get("/{article_id}", response_model=ArticleOut)
async def get_article(
    article_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = (
        await db.execute(
            select(Article).where(
                Article.id == article_id, Article.user_id == current_user.id
            )
        )
    ).scalars().first()
    if not article:
        raise HTTPException(404, "文献不存在")
    article.is_read = True
    await db.commit()
    keyword_map = await _keyword_map(db, [article.id], current_user.id)
    return _to_out(article, keyword_map.get(article.id))


@router.get("/{article_id}/download")
async def download_article(
    article_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = (
        await db.execute(
            select(Article).where(
                Article.id == article_id, Article.user_id == current_user.id
            )
        )
    ).scalars().first()
    if not article:
        raise HTTPException(404, "文献不存在")
    if not article.file_path or not os.path.exists(article.file_path):
        raise HTTPException(404, "文件不存在")
    suffix = article.file_type or "pdf"
    filename = f"{article.title[:50]}.{suffix}"
    return FileResponse(
        article.file_path,
        filename=filename,
        media_type=article.mime_type or "application/octet-stream",
    )


@router.delete("/{article_id}")
async def delete_article(
    article_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = (
        await db.execute(
            select(Article).where(
                Article.id == article_id, Article.user_id == current_user.id
            )
        )
    ).scalars().first()
    if not article:
        raise HTTPException(404, "文献不存在")
    if article.file_path and os.path.exists(article.file_path):
        os.remove(article.file_path)
    await db.execute(
        update(CrawlItem).where(CrawlItem.article_id == article_id).values(article_id=None)
    )
    await db.execute(
        update(AnalysisResult)
        .where(
            AnalysisResult.article_id == article_id,
            AnalysisResult.user_id == current_user.id,
        )
        .values(article_id=None)
    )
    await db.execute(
        delete(ArticleKeyword).where(ArticleKeyword.article_id == article_id)
    )
    await db.delete(article)
    await db.commit()
    return {"message": "已删除"}


@router.put("/{article_id}/star")
async def toggle_star(
    article_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = (
        await db.execute(
            select(Article).where(
                Article.id == article_id, Article.user_id == current_user.id
            )
        )
    ).scalars().first()
    if not article:
        raise HTTPException(404, "文献不存在")
    article.is_starred = not article.is_starred
    await db.commit()
    return {"is_starred": article.is_starred}

"""Keyword strategy management routes."""
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import AnalysisResult, Article, ArticleKeyword, CrawlLog, Keyword, User
from schemas import KeywordCreate, KeywordOut, KeywordUpdate, QueryPreview
from services.crawler_service import build_query_plan
from services.auth_service import get_current_user

router = APIRouter(prefix="/api/keywords", tags=["关键词"])


def _clean_strings(values: list[str] | None) -> list[str]:
    seen = set()
    output = []
    for value in values or []:
        cleaned = value.strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            output.append(cleaned)
    return output


def _clean_payload(payload: dict) -> dict:
    for field in ("aliases", "exact_phrases", "excluded_terms", "site_filters"):
        if field in payload and payload[field] is not None:
            payload[field] = _clean_strings(payload[field])
    if "source_ids" in payload and payload["source_ids"] is not None:
        payload["source_ids"] = list(dict.fromkeys(payload["source_ids"]))
    if payload.get("keyword"):
        payload["keyword"] = payload["keyword"].strip()
    return payload


async def _to_out(keyword: Keyword, db: AsyncSession) -> KeywordOut:
    count = (
        await db.execute(
            select(func.count(ArticleKeyword.article_id))
            .join(Article, Article.id == ArticleKeyword.article_id)
            .where(
                ArticleKeyword.keyword_id == keyword.id,
                Article.user_id == keyword.user_id,
            )
        )
    ).scalar() or 0
    return KeywordOut.model_validate({**keyword.__dict__, "article_count": count})


@router.get("", response_model=list[KeywordOut])
async def list_keywords(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    keywords = (
        await db.execute(
            select(Keyword)
            .where(Keyword.user_id == current_user.id)
            .order_by(Keyword.created_at.desc())
        )
    ).scalars().all()
    return [await _to_out(keyword, db) for keyword in keywords]


@router.post("/preview", response_model=QueryPreview)
async def preview_keyword(
    data: KeywordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payload = _clean_payload(data.model_dump())
    keyword = Keyword(user_id=current_user.id, **payload)
    queries = await build_query_plan(keyword, db)
    return QueryPreview(queries=queries)


@router.post("", response_model=KeywordOut)
async def create_keyword(
    data: KeywordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payload = _clean_payload(data.model_dump())
    duplicate = await db.execute(
        select(Keyword).where(
            Keyword.user_id == current_user.id,
            func.lower(Keyword.keyword) == payload["keyword"].lower(),
        )
    )
    if duplicate.scalars().first():
        raise HTTPException(409, "核心关键词已存在")
    keyword = Keyword(user_id=current_user.id, **payload)
    db.add(keyword)
    await db.commit()
    await db.refresh(keyword)
    return await _to_out(keyword, db)


@router.put("/{keyword_id}", response_model=KeywordOut)
async def update_keyword(
    keyword_id: int,
    data: KeywordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    keyword = (
        await db.execute(
            select(Keyword).where(
                Keyword.id == keyword_id, Keyword.user_id == current_user.id
            )
        )
    ).scalars().first()
    if not keyword:
        raise HTTPException(404, "关键词不存在")
    payload = _clean_payload(data.model_dump(exclude_unset=True))
    if payload.get("keyword"):
        duplicate = await db.execute(
            select(Keyword).where(
                func.lower(Keyword.keyword) == payload["keyword"].lower(),
                Keyword.user_id == current_user.id,
                Keyword.id != keyword_id,
            )
        )
        if duplicate.scalars().first():
            raise HTTPException(409, "核心关键词已存在")
    for field, value in payload.items():
        setattr(keyword, field, value)
    await db.commit()
    await db.refresh(keyword)
    return await _to_out(keyword, db)


@router.delete("/{keyword_id}")
async def delete_keyword(
    keyword_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    keyword = (
        await db.execute(
            select(Keyword).where(
                Keyword.id == keyword_id, Keyword.user_id == current_user.id
            )
        )
    ).scalars().first()
    if not keyword:
        raise HTTPException(404, "关键词不存在")

    primary_articles = (
        await db.execute(
            select(Article).where(
                Article.keyword_id == keyword_id, Article.user_id == current_user.id
            )
        )
    ).scalars().all()
    for article in primary_articles:
        replacement = (
            await db.execute(
                select(ArticleKeyword.keyword_id).where(
                    ArticleKeyword.article_id == article.id,
                    ArticleKeyword.keyword_id != keyword_id,
                ).join(Keyword, Keyword.id == ArticleKeyword.keyword_id)
                .where(Keyword.user_id == current_user.id)
                .limit(1)
            )
        ).scalar()
        if replacement:
            article.keyword_id = replacement
        else:
            if article.file_path and os.path.exists(article.file_path):
                os.remove(article.file_path)
            await db.delete(article)

    await db.execute(
        delete(ArticleKeyword).where(ArticleKeyword.keyword_id == keyword_id)
    )
    await db.execute(
        update(CrawlLog)
        .where(CrawlLog.keyword_id == keyword_id, CrawlLog.user_id == current_user.id)
        .values(keyword_id=None)
    )
    await db.execute(
        update(AnalysisResult)
        .where(
            AnalysisResult.keyword_id == keyword_id,
            AnalysisResult.user_id == current_user.id,
        )
        .values(keyword_id=None)
    )
    await db.delete(keyword)
    await db.commit()
    return {"message": "已删除"}

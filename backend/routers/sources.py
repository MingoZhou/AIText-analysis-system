"""Data source management routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import CrawlItem, DataSource, Keyword, User
from schemas import DataSourceCreate, DataSourceOut, DataSourceUpdate
from services.auth_service import get_current_user

router = APIRouter(prefix="/api/sources", tags=["数据源"])


@router.get("", response_model=list[DataSourceOut])
async def list_sources(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(DataSource)
        .where(DataSource.user_id == current_user.id)
        .order_by(DataSource.priority, DataSource.id)
    )
    return result.scalars().all()


@router.post("", response_model=DataSourceOut)
async def create_source(
    data: DataSourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source = DataSource(user_id=current_user.id, **data.model_dump())
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


@router.put("/{source_id}", response_model=DataSourceOut)
async def update_source(
    source_id: int,
    data: DataSourceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source = (
        await db.execute(
            select(DataSource).where(
                DataSource.id == source_id, DataSource.user_id == current_user.id
            )
        )
    ).scalars().first()
    if not source:
        raise HTTPException(404, "数据源不存在")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(source, field, value)
    await db.commit()
    await db.refresh(source)
    return source


@router.delete("/{source_id}")
async def delete_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source = (
        await db.execute(
            select(DataSource).where(
                DataSource.id == source_id, DataSource.user_id == current_user.id
            )
        )
    ).scalars().first()
    if not source:
        raise HTTPException(404, "数据源不存在")

    keywords = (
        await db.execute(select(Keyword).where(Keyword.user_id == current_user.id))
    ).scalars().all()
    for keyword in keywords:
        current = list(keyword.source_ids or [])
        if source_id in current:
            keyword.source_ids = [item for item in current if item != source_id]

    await db.execute(
        update(CrawlItem).where(CrawlItem.source_id == source_id).values(source_id=None)
    )

    await db.delete(source)
    await db.commit()
    return {"message": "已删除"}

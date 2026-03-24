from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime
from app.database import get_db
from app.api.routes.auth import verify_token
from app.models import KnowledgeItem, KnowledgeCategory

router = APIRouter()


class KnowledgeCategoryCreate(BaseModel):
    name: str
    order: int = 0


class KnowledgeCreate(BaseModel):
    title: str
    content: str
    tags: str = ""
    category: str = "Общее"


@router.get("/categories")
async def get_categories(db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    result = await db.execute(select(KnowledgeCategory).order_by(KnowledgeCategory.order))
    cats = result.scalars().all()
    # Also include legacy string categories from items
    result2 = await db.execute(select(KnowledgeItem.category).distinct())
    legacy = {row[0] for row in result2.fetchall() if row[0]}
    existing_names = {c.name for c in cats}
    return [
        {"id": c.id, "name": c.name, "order": c.order} for c in cats
    ] + [
        {"id": None, "name": name, "order": 99} for name in sorted(legacy - existing_names)
    ]


@router.post("/categories")
async def create_category(body: KnowledgeCategoryCreate, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    cat = KnowledgeCategory(name=body.name, order=body.order)
    db.add(cat)
    await db.flush()
    await db.commit()
    return {"id": cat.id, "name": cat.name, "order": cat.order}


@router.delete("/categories/{cat_id}")
async def delete_category(cat_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    cat = await db.get(KnowledgeCategory, cat_id)
    if cat:
        await db.delete(cat)
        await db.commit()
    return {"ok": True}


@router.get("/")
async def get_all(db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    result = await db.execute(select(KnowledgeItem).order_by(KnowledgeItem.updated_at.desc()))
    items = result.scalars().all()
    return [_to_dict(i) for i in items]


@router.post("/")
async def create(body: KnowledgeCreate, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    item = KnowledgeItem(
        title=body.title, content=body.content,
        tags=body.tags, category=body.category,
        updated_at=datetime.utcnow(),
    )
    db.add(item)
    await db.flush()
    await db.commit()
    return _to_dict(item)


@router.patch("/{item_id}")
async def update(item_id: int, body: KnowledgeCreate, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    item = await db.get(KnowledgeItem, item_id)
    if not item:
        raise HTTPException(404, "Not found")
    item.title = body.title
    item.content = body.content
    item.tags = body.tags
    item.category = body.category
    item.updated_at = datetime.utcnow()
    await db.commit()
    return _to_dict(item)


@router.delete("/{item_id}")
async def delete(item_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    item = await db.get(KnowledgeItem, item_id)
    if item:
        await db.delete(item)
        await db.commit()
    return {"ok": True}


def _to_dict(i: KnowledgeItem) -> dict:
    return {
        "id": i.id, "title": i.title, "content": i.content,
        "tags": i.tags.split(",") if i.tags else [],
        "category": i.category,
        "updated_at": i.updated_at.isoformat(),
    }


@router.get("/")
async def get_all(db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    result = await db.execute(select(KnowledgeItem).order_by(KnowledgeItem.updated_at.desc()))
    items = result.scalars().all()
    return [_to_dict(i) for i in items]


@router.post("/")
async def create(body: KnowledgeCreate, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    item = KnowledgeItem(
        title=body.title, content=body.content,
        tags=body.tags, category=body.category,
        updated_at=datetime.utcnow(),
    )
    db.add(item)
    await db.flush()
    return _to_dict(item)


@router.patch("/{item_id}")
async def update(item_id: int, body: KnowledgeCreate, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    item = await db.get(KnowledgeItem, item_id)
    if not item:
        raise HTTPException(404, "Not found")
    item.title = body.title
    item.content = body.content
    item.tags = body.tags
    item.category = body.category
    item.updated_at = datetime.utcnow()
    return _to_dict(item)


@router.delete("/{item_id}")
async def delete(item_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    item = await db.get(KnowledgeItem, item_id)
    if item:
        await db.delete(item)
    return {"ok": True}


def _to_dict(i: KnowledgeItem) -> dict:
    return {
        "id": i.id, "title": i.title, "content": i.content,
        "tags": i.tags.split(",") if i.tags else [],
        "category": i.category,
        "updated_at": i.updated_at.isoformat(),
    }

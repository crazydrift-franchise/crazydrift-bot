"""FAQ routes"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Any
from app.database import get_db
from app.repositories.faq_repo import FaqRepository
from app.api.routes.auth import verify_token
from app.models import FaqCategory, FaqItem
import json

router = APIRouter()


class CategoryCreate(BaseModel):
    name: str
    order: int = 0
    is_active: bool = True


class ButtonConfig(BaseModel):
    id: str
    label: str
    type: str  # "link" | "gpt"
    value: str = ""  # URL for link, question hint for gpt


class ItemCreate(BaseModel):
    category_id: int
    question: str
    answer: str
    order: int = 0
    is_active: bool = True
    followup_enabled: bool = False
    followup_delay_hours: int = 24
    followup_text: str | None = None
    followup_buttons: list[Any] | None = None


def _item_to_dict(i: FaqItem) -> dict:
    buttons = None
    if i.followup_buttons:
        try:
            buttons = json.loads(i.followup_buttons)
        except Exception:
            buttons = None
    return {
        "id": i.id,
        "category_id": i.category_id,
        "question": i.question,
        "answer": i.answer,
        "order": i.order,
        "is_active": i.is_active,
        "followup_enabled": i.followup_enabled,
        "followup_delay_hours": i.followup_delay_hours,
        "followup_text": i.followup_text,
        "followup_buttons": buttons,
    }


@router.get("/categories")
async def get_categories(db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    repo = FaqRepository(db)
    cats = await repo.get_all_categories()
    return [{"id": c.id, "name": c.name, "order": c.order, "is_active": c.is_active} for c in cats]


@router.post("/categories")
async def create_category(body: CategoryCreate, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    repo = FaqRepository(db)
    cat = await repo.create_category(body.name, body.order)
    return {"id": cat.id, "name": cat.name}


@router.patch("/categories/{cat_id}")
async def update_category(cat_id: int, body: CategoryCreate, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    cat = await db.get(FaqCategory, cat_id)
    if not cat:
        raise HTTPException(404, "Not found")
    cat.name = body.name
    cat.order = body.order
    cat.is_active = body.is_active
    await db.commit()
    return {"ok": True}


@router.delete("/categories/{cat_id}")
async def delete_category(cat_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    cat = await db.get(FaqCategory, cat_id)
    if cat:
        await db.delete(cat)
        await db.commit()
    return {"ok": True}


@router.get("/items")
async def get_items(db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    result = await db.execute(select(FaqItem))
    return [_item_to_dict(i) for i in result.scalars().all()]


@router.post("/items")
async def create_item(body: ItemCreate, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    repo = FaqRepository(db)
    item = await repo.create_item(body.category_id, body.question, body.answer, body.order)
    item.followup_enabled = body.followup_enabled
    item.followup_delay_hours = body.followup_delay_hours
    item.followup_text = body.followup_text
    item.followup_buttons = json.dumps(body.followup_buttons) if body.followup_buttons else None
    await db.commit()
    return _item_to_dict(item)


@router.patch("/items/{item_id}")
async def update_item(item_id: int, body: ItemCreate, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    item = await db.get(FaqItem, item_id)
    if not item:
        raise HTTPException(404, "Not found")
    item.question = body.question
    item.answer = body.answer
    item.order = body.order
    item.is_active = body.is_active
    item.category_id = body.category_id
    item.followup_enabled = body.followup_enabled
    item.followup_delay_hours = body.followup_delay_hours
    item.followup_text = body.followup_text
    item.followup_buttons = json.dumps(body.followup_buttons) if body.followup_buttons else None
    await db.commit()
    return _item_to_dict(item)


@router.delete("/items/{item_id}")
async def delete_item(item_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    item = await db.get(FaqItem, item_id)
    if item:
        await db.delete(item)
        await db.commit()
    return {"ok": True}

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.database import get_db
from app.api.routes.auth import verify_token
from app.models import Touch

router = APIRouter()


class TouchCreate(BaseModel):
    name: str
    is_active: bool = True
    send_mode: str = "static"
    reply_mode: str = "none"
    schedule: str = ""
    segment: str = "all"
    message_text: str = ""
    gpt_prompt: str = ""


@router.get("/")
async def get_all(db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    result = await db.execute(select(Touch).order_by(Touch.created_at))
    return [_to_dict(t) for t in result.scalars().all()]


@router.post("/")
async def create(body: TouchCreate, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    touch = Touch(**body.model_dump())
    db.add(touch)
    await db.flush()
    return _to_dict(touch)


@router.patch("/{touch_id}")
async def update(touch_id: int, body: TouchCreate, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    touch = await db.get(Touch, touch_id)
    if not touch:
        raise HTTPException(404, "Not found")
    for k, v in body.model_dump().items():
        setattr(touch, k, v)
    return _to_dict(touch)


@router.delete("/{touch_id}")
async def delete(touch_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    touch = await db.get(Touch, touch_id)
    if touch:
        await db.delete(touch)
    return {"ok": True}


def _to_dict(t: Touch) -> dict:
    return {
        "id": t.id, "name": t.name, "is_active": t.is_active,
        "send_mode": t.send_mode, "reply_mode": t.reply_mode,
        "schedule": t.schedule, "segment": t.segment,
        "message_text": t.message_text, "gpt_prompt": t.gpt_prompt,
        "sent_count": t.sent_count,
        "created_at": t.created_at.isoformat(),
    }

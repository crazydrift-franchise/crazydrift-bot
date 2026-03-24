from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.database import get_db
from app.api.routes.auth import verify_token
from app.models import Broadcast, BroadcastStatus
import json

router = APIRouter()


class CreateBroadcast(BaseModel):
    text: str
    scheduled_at: str  # ISO string
    filters: dict | None = None


@router.get("/")
async def list_broadcasts(db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    result = await db.execute(select(Broadcast).order_by(Broadcast.scheduled_at.asc()))
    broadcasts = result.scalars().all()
    return [_bc_to_dict(b) for b in broadcasts]


@router.post("/")
async def create_broadcast(body: CreateBroadcast, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    bc = Broadcast(
        text=body.text,
        scheduled_at=datetime.fromisoformat(body.scheduled_at),
        filters=json.dumps(body.filters) if body.filters else None,
        status=BroadcastStatus.scheduled,
    )
    db.add(bc)
    await db.commit()
    await db.refresh(bc)
    return _bc_to_dict(bc)


@router.delete("/{bc_id}")
async def cancel_broadcast(bc_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    bc = await db.get(Broadcast, bc_id)
    if not bc:
        raise HTTPException(404, "Not found")
    if bc.status == BroadcastStatus.sent:
        raise HTTPException(400, "Already sent")
    bc.status = BroadcastStatus.cancelled
    await db.commit()
    return {"ok": True}


def _bc_to_dict(b: Broadcast) -> dict:
    return {
        "id": b.id,
        "text": b.text,
        "scheduled_at": b.scheduled_at.isoformat(),
        "sent_at": b.sent_at.isoformat() if b.sent_at else None,
        "status": b.status.value,
        "filters": json.loads(b.filters) if b.filters else None,
        "sent_count": b.sent_count,
        "failed_count": b.failed_count,
        "created_at": b.created_at.isoformat(),
    }

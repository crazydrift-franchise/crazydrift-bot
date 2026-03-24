from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.database import get_db
from app.api.routes.auth import verify_token
from app.models import LeadNote, Lead
from app.services.notifications import notify_manager

router = APIRouter()


class NoteCreate(BaseModel):
    content: str
    remind_at: Optional[str] = None


@router.get("/{lead_id}/notes")
async def get_notes(lead_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    result = await db.execute(
        select(LeadNote).where(LeadNote.lead_id == lead_id).order_by(LeadNote.created_at.desc())
    )
    notes = result.scalars().all()
    return [_note_to_dict(n) for n in notes]


@router.post("/{lead_id}/notes")
async def create_note(
    lead_id: int,
    body: NoteCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")

    remind_at = None
    if body.remind_at:
        try:
            remind_at = datetime.fromisoformat(body.remind_at)
        except ValueError:
            raise HTTPException(400, "Invalid datetime format")

    note = LeadNote(
        lead_id=lead_id,
        content=body.content,
        remind_at=remind_at,
    )
    db.add(note)
    await db.flush()
    await db.commit()

    # Уведомление при создании заметки с напоминанием
    if remind_at:
        lead_name = getattr(lead, "name", None) or f"Лид #{lead_id}"
        remind_str = remind_at.strftime("%d.%m.%Y %H:%M")
        city = getattr(lead, "city", None) or "—"
        lead_link = f"https://panel-crazyfr.ru/leads/{lead_id}"
        await notify_manager(
            f"📝 *Новая заметка*\n"
            f"Лид: {lead_name}\n"
            f"Город: {city}\n"
            f"Заметка: {body.content[:200]}\n"
            f"Напоминание: {remind_str}\n"
            f"[Открыть карточку]({lead_link})"
        )
        # Автоматически создаём задачу
        from app.models import Task, TaskPriority, TaskStatus
        task = Task(
            title=f"Напоминание: {lead_name}",
            description=body.content[:500],
            lead_id=lead_id,
            priority=TaskPriority.medium,
            status=TaskStatus.todo,
            due_at=remind_at,
        )
        db.add(task)
        await db.commit()

    return _note_to_dict(note)


@router.delete("/{lead_id}/notes/{note_id}")
async def delete_note(
    lead_id: int,
    note_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    note = await db.get(LeadNote, note_id)
    if note and note.lead_id == lead_id:
        await db.delete(note)
    return {"ok": True}


def _note_to_dict(n: LeadNote) -> dict:
    return {
        "id": n.id,
        "lead_id": n.lead_id,
        "content": n.content,
        "remind_at": n.remind_at.isoformat() if n.remind_at else None,
        "created_at": n.created_at.isoformat(),
    }

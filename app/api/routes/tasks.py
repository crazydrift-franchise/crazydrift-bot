from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.database import get_db
from app.api.routes.auth import verify_token
from app.models import Task, TaskStatus, TaskPriority, Lead

router = APIRouter()


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    lead_id: Optional[int] = None
    priority: str = "medium"
    due_at: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_at: Optional[str] = None
    lead_id: Optional[int] = None


@router.get("/")
async def get_tasks(db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    result = await db.execute(
        select(Task).order_by(Task.due_at.asc().nullslast(), Task.created_at.desc())
    )
    tasks = result.scalars().all()
    # Enrich with lead name
    out = []
    for t in tasks:
        d = _task_to_dict(t)
        if t.lead_id:
            lead = await db.get(Lead, t.lead_id)
            d["lead_name"] = lead.name if lead else None
        out.append(d)
    return out


@router.post("/")
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    due_at = None
    if body.due_at:
        try:
            due_at = datetime.fromisoformat(body.due_at)
        except ValueError:
            raise HTTPException(400, "Invalid datetime")

    try:
        priority = TaskPriority(body.priority)
    except ValueError:
        priority = TaskPriority.medium

    task = Task(
        title=body.title,
        description=body.description,
        lead_id=body.lead_id,
        priority=priority,
        due_at=due_at,
    )
    db.add(task)
    await db.flush()
    await db.commit()

    # Notify manager
    if body.lead_id:
        lead = await db.get(Lead, body.lead_id)
        lead_name = lead.name if lead else f"Лид #{body.lead_id}"
    else:
        lead_name = None

    from app.services.notifications import notify_manager
    due_str = due_at.strftime("%d.%m.%Y %H:%M") if due_at else "без срока"
    await notify_manager(
        f"✅ *Новая задача*\n"
        f"Задача: {body.title}\n"
        f"{f'Лид: {lead_name}' if lead_name else ''}\n"
        f"Срок: {due_str}\n"
        f"Приоритет: {priority.value}"
    )

    return _task_to_dict(task)


@router.patch("/{task_id}")
async def update_task(
    task_id: int,
    body: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Not found")

    if body.title is not None:
        task.title = body.title
    if body.description is not None:
        task.description = body.description
    if body.lead_id is not None:
        task.lead_id = body.lead_id
    if body.status is not None:
        try:
            task.status = TaskStatus(body.status)
            if task.status == TaskStatus.done:
                task.done_at = datetime.utcnow()
        except ValueError:
            raise HTTPException(400, "Invalid status")
    if body.priority is not None:
        try:
            task.priority = TaskPriority(body.priority)
        except ValueError:
            pass
    if body.due_at is not None:
        try:
            task.due_at = datetime.fromisoformat(body.due_at)
        except ValueError:
            raise HTTPException(400, "Invalid datetime")

    task.updated_at = datetime.utcnow()
    await db.commit()
    return _task_to_dict(task)


@router.delete("/{task_id}")
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    task = await db.get(Task, task_id)
    if task:
        await db.delete(task)
        await db.commit()
    return {"ok": True}


def _task_to_dict(t: Task) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "description": t.description,
        "lead_id": t.lead_id,
        "lead_name": None,
        "status": t.status.value if t.status else "todo",
        "priority": t.priority.value if t.priority else "medium",
        "due_at": t.due_at.isoformat() if t.due_at else None,
        "done_at": t.done_at.isoformat() if t.done_at else None,
        "created_at": t.created_at.isoformat(),
    }

"""Recommendations API — просмотр GPT переписки + анализ выбранных сообщений."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.database import get_db
from app.api.routes.auth import verify_token
from app.models import KnowledgeRecommendation
import json, logging

router = APIRouter()
logger = logging.getLogger(__name__)
PANEL_URL = "https://panel-crazyfr.ru"


# ── Get GPT messages list (for selection) ─────────────────────────────────────

@router.get("/messages")
async def get_gpt_messages(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    lead_status: Optional[str] = None,
    lead_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    """Get all GPT-processed messages for selection."""
    from sqlalchemy import select, and_
    from app.models import LeadEvent, Lead, User

    q = (
        select(LeadEvent, Lead, User)
        .join(Lead, LeadEvent.lead_id == Lead.id)
        .join(User, Lead.user_id == User.id)
        .where(LeadEvent.event_type == "message")
    )

    if lead_id:
        q = q.where(LeadEvent.lead_id == lead_id)
    if date_from:
        try:
            q = q.where(LeadEvent.created_at >= datetime.fromisoformat(date_from))
        except Exception:
            pass
    if date_to:
        try:
            q = q.where(LeadEvent.created_at <= datetime.fromisoformat(date_to + "T23:59:59"))
        except Exception:
            pass
    if lead_status and lead_status != "all":
        from app.models import LeadStatus
        try:
            q = q.where(Lead.status == LeadStatus(lead_status))
        except Exception:
            pass

    q = q.order_by(LeadEvent.created_at.desc()).limit(500)
    result = await db.execute(q)
    rows = result.all()

    # For each user message, find the next gpt_reply
    # Get all gpt replies in same timeframe
    gpt_result = await db.execute(
        select(LeadEvent)
        .where(LeadEvent.event_type == "gpt_reply")
        .order_by(LeadEvent.created_at.asc())
    )
    gpt_events = {e.lead_id: {} for e in gpt_result.scalars().all()}

    # Re-query gpt replies properly
    gpt_q = select(LeadEvent).where(LeadEvent.event_type == "gpt_reply").order_by(LeadEvent.created_at.asc())
    gpt_res = await db.execute(gpt_q)
    gpt_list = gpt_res.scalars().all()

    # Map lead_id -> list of gpt events sorted by time
    from collections import defaultdict
    gpt_by_lead: dict = defaultdict(list)
    for g in gpt_list:
        gpt_by_lead[g.lead_id].append(g)

    messages = []
    for row in rows:
        event, lead, user = row[0], row[1], row[2]
        if not event.event_data:
            continue

        # Find closest GPT reply after this message
        ai_reply = None
        for g in gpt_by_lead.get(event.lead_id, []):
            if g.created_at > event.created_at:
                ai_reply = g.event_data
                break

        if not ai_reply:
            continue  # Only show messages that got GPT reply

        messages.append({
            "event_id": event.id,
            "lead_id": lead.id,
            "lead_name": lead.name or f"Лид #{lead.id}",
            "lead_status": lead.status.value if lead.status else "new",
            "lead_url": f"{PANEL_URL}/leads/{lead.id}",
            "message": event.event_data[:1000],
            "ai_response": ai_reply[:1000] if ai_reply else None,
            "created_at": event.created_at.isoformat(),
        })

    return messages


# ── Analyze selected messages ──────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    event_ids: List[int]
    lead_id: Optional[int] = None  # если анализ из карточки лида


@router.post("/analyze")
async def analyze_selected_messages(
    body: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    """Analyze selected GPT messages → generate 3 answer variants per message."""
    from sqlalchemy import select
    from app.models import LeadEvent, Lead, User, FaqItem, KnowledgeItem
    from app.services.ai.claude_service import _call_claude

    if not body.event_ids:
        raise HTTPException(400, "No events selected")

    # Get selected events
    events_result = await db.execute(
        select(LeadEvent, Lead)
        .join(Lead, LeadEvent.lead_id == Lead.id)
        .where(LeadEvent.id.in_(body.event_ids))
    )
    rows = events_result.all()

    if not rows:
        return {"recommendations": [], "new_count": 0}

    # Get GPT replies for context
    gpt_result = await db.execute(
        select(LeadEvent).where(
            LeadEvent.event_type == "gpt_reply",
            LeadEvent.lead_id.in_([r[1].id for r in rows])
        ).order_by(LeadEvent.created_at.asc())
    )
    from collections import defaultdict
    gpt_by_lead: dict = defaultdict(list)
    for g in gpt_result.scalars().all():
        gpt_by_lead[g.lead_id].append(g)

    # Get existing FAQ/KB for context
    faq_res = await db.execute(select(FaqItem).where(FaqItem.is_active == True))
    faq_items = faq_res.scalars().all()
    kb_res = await db.execute(select(KnowledgeItem))
    kb_items = kb_res.scalars().all()
    existing = "\n".join(
        [f"FAQ: {f.question}" for f in faq_items[:30]] +
        [f"KB: {k.title}" for k in kb_items[:20]]
    )

    # Get GPT system prompt
    from app.repositories.gpt_settings_repo import GPTSettingsRepository
    gpt_repo = GPTSettingsRepository(db)
    gpt_settings = await gpt_repo.get_or_create()
    system_prompt = gpt_settings.system_prompt or "Ты эксперт по франшизе CrazyDrift."

    saved = []
    for row in rows:
        event, lead = row[0], row[1]
        if not event.event_data:
            continue

        # Find AI response
        ai_reply = None
        for g in gpt_by_lead.get(lead.id, []):
            if g.created_at > event.created_at:
                ai_reply = g.event_data
                break

        msg = event.event_data[:500]
        ai_resp = (ai_reply or "")[:300]

        prompt = f"""Системный промт бота: {system_prompt[:200]}

Существующий контент (FAQ/KB):
{existing[:1000]}

Вопрос лида: {msg}
Текущий ответ AI: {ai_resp}

Твоя задача: предложи 3 РАЗНЫХ варианта ответа на вопрос лида для добавления в FAQ или базу знаний.
Варианты должны быть разными по стилю: 1) краткий, 2) подробный, 3) с конкретными цифрами/фактами.
Укажи тип контента (faq или knowledge_base) и приоритет (high/medium/low).

Ответь ТОЛЬКО валидным JSON:
{{"question": "краткая формулировка вопроса", "type": "faq", "priority": "high", "variant_1": "краткий ответ", "variant_2": "подробный ответ", "variant_3": "ответ с цифрами/фактами"}}"""

        try:
            response = await _call_claude(prompt, max_tokens=800)
            import re
            json_match = re.search(r'\{[\s\S]*?\}', response)
            if not json_match:
                continue
            data = json.loads(json_match.group())
        except Exception as e:
            logger.error(f"analyze message {event.id} error: {e}")
            continue

        # Check duplicate
        dup = await db.execute(
            select(KnowledgeRecommendation).where(
                KnowledgeRecommendation.lead_event_id == event.id
            )
        )
        if dup.scalars().first():
            continue

        rec = KnowledgeRecommendation(
            lead_id=lead.id,
            lead_event_id=event.id,
            recommendation_type=data.get("type", "faq"),
            lead_message=msg,
            ai_response=ai_resp or None,
            message_date=event.created_at,
            lead_status=lead.status.value if lead.status else "new",
            question=data.get("question", msg[:100]),
            answer_variant_1=data.get("variant_1"),
            answer_variant_2=data.get("variant_2"),
            answer_variant_3=data.get("variant_3"),
            priority=data.get("priority", "medium"),
        )
        db.add(rec)
        saved.append(rec)

    await db.commit()
    for r in saved:
        await db.refresh(r)

    all_result = await db.execute(
        select(KnowledgeRecommendation)
        .where(KnowledgeRecommendation.is_applied == False)
        .order_by(KnowledgeRecommendation.created_at.desc())
    )
    all_recs = all_result.scalars().all()

    return {
        "new_count": len(saved),
        "total": len(all_recs),
        "recommendations": [_rec_to_dict(r) for r in all_recs],
    }


# ── CRUD ───────────────────────────────────────────────────────────────────────

@router.get("/")
async def get_recommendations(
    applied: bool = False,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    result = await db.execute(
        select(KnowledgeRecommendation)
        .where(KnowledgeRecommendation.is_applied == applied)
        .order_by(KnowledgeRecommendation.created_at.desc())
    )
    return [_rec_to_dict(r) for r in result.scalars().all()]


@router.post("/{rec_id}/apply")
async def apply_recommendation(rec_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    rec = await db.get(KnowledgeRecommendation, rec_id)
    if not rec:
        raise HTTPException(404, "Not found")
    rec.is_applied = True
    rec.applied_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}


@router.post("/{rec_id}/unapply")
async def unapply_recommendation(rec_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    rec = await db.get(KnowledgeRecommendation, rec_id)
    if not rec:
        raise HTTPException(404, "Not found")
    rec.is_applied = False
    rec.applied_at = None
    await db.commit()
    return {"ok": True}


@router.delete("/{rec_id}")
async def delete_recommendation(rec_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    rec = await db.get(KnowledgeRecommendation, rec_id)
    if rec:
        await db.delete(rec)
        await db.commit()
    return {"ok": True}


def _rec_to_dict(r: KnowledgeRecommendation) -> dict:
    return {
        "id": r.id,
        "type": r.recommendation_type,
        "lead_id": r.lead_id,
        "lead_message": r.lead_message,
        "ai_response": r.ai_response,
        "message_date": r.message_date.isoformat() if r.message_date else None,
        "lead_status": r.lead_status,
        "question": r.question,
        "answer_variant_1": r.answer_variant_1,
        "answer_variant_2": r.answer_variant_2,
        "answer_variant_3": r.answer_variant_3,
        "priority": r.priority,
        "is_applied": r.is_applied,
        "applied_at": r.applied_at.isoformat() if r.applied_at else None,
        "created_at": r.created_at.isoformat(),
    }

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import csv
import io
from app.database import get_db
from app.repositories.lead_repo import LeadRepository
from app.repositories.faq_repo import KnowledgeRepository, GptSettingsRepository
from app.services.ai.claude_service import analyze_lead
from app.api.routes.auth import verify_token
from app.models import LeadStatus, LeadEvent, User, Lead

router = APIRouter()


class UpdateStatusRequest(BaseModel):
    status: str


class UpdateLeadRequest(BaseModel):
    manager_notes: Optional[str] = None
    reminder_at: Optional[str] = None
    is_blocked: Optional[bool] = None
    block_reason: Optional[str] = None
    status: Optional[str] = None


class BroadcastRequest(BaseModel):
    text: str
    segment: str = "all"


@router.get("/blocked")
async def get_blocked(db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models import Lead
    result = await db.execute(
        select(Lead).options(selectinload(Lead.user))
        .where(Lead.is_blocked == True)
        .order_by(Lead.updated_at.desc())
    )
    return [_lead_to_dict(l) for l in result.scalars().all()]


@router.get("/{lead_id}/last-events")
async def get_last_events(
    lead_id: int, limit: int = 10,
    db: AsyncSession = Depends(get_db), _=Depends(verify_token),
):
    from sqlalchemy import select
    result = await db.execute(
        select(LeadEvent).where(LeadEvent.lead_id == lead_id)
        .order_by(LeadEvent.created_at.desc()).limit(limit)
    )
    return [{"event_type": e.event_type.value, "event_data": e.event_data, "created_at": e.created_at.isoformat()} for e in result.scalars().all()]


@router.get("/")
async def get_leads(
    skip: int = 0, limit: int = 200,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    repo = LeadRepository(db)
    leads = await repo.get_all_leads(skip=skip, limit=limit)
    return [_lead_to_dict(l) for l in leads]


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    repo = LeadRepository(db)
    return await repo.get_stats()


@router.get("/export-csv")
async def export_csv(db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    """Экспорт всех лидов в CSV."""
    repo = LeadRepository(db)
    leads = await repo.get_all_leads(skip=0, limit=10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Имя", "Город", "Интерес", "Телефон", "Username",
                     "Статус", "Температура", "Engagement", "UTM source",
                     "UTM campaign", "Заметки", "Дата"])
    for lead in leads:
        writer.writerow([
            lead.id, lead.name or "", lead.city or "", lead.need or "",
            lead.phone or "", lead.user.username if lead.user else "",
            lead.status.value if lead.status else "",
            lead.lead_temperature.value if lead.lead_temperature else "",
            lead.engagement_score,
            getattr(lead, "utm_source", "") or "",
            getattr(lead, "utm_campaign", "") or "",
            getattr(lead, "manager_notes", "") or "",
            lead.created_at.strftime("%d.%m.%Y %H:%M"),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )


@router.post("/broadcast")
async def broadcast(
    body: BroadcastRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    """Ручная рассылка по сегменту."""
    from app.services.notifications import _bot
    if not _bot:
        raise HTTPException(503, "Bot not available")

    repo = LeadRepository(db)
    leads = await repo.get_leads_by_segment(body.segment)

    sent = 0
    failed = 0
    for lead in leads:
        if not lead.user or not lead.user.telegram_user_id:
            continue
        if getattr(lead, "is_blocked", False):
            continue
        try:
            await _bot.send_message(chat_id=lead.user.telegram_user_id, text=body.text)
            from app.models import EventType
            await repo.add_event(lead.id, EventType.touch, f"Broadcast: {body.text[:80]}")
            sent += 1
        except Exception:
            failed += 1

    await db.commit()
    return {"sent": sent, "failed": failed, "total": len(leads)}


@router.get("/{lead_id}")
async def get_lead(lead_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    repo = LeadRepository(db)
    lead = await repo.get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return _lead_to_dict(lead)


@router.patch("/{lead_id}")
async def update_lead(
    lead_id: int,
    body: UpdateLeadRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    repo = LeadRepository(db)
    lead = await repo.get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    updates = {}
    if body.manager_notes is not None:
        updates["manager_notes"] = body.manager_notes
    if body.is_blocked is not None:
        updates["is_blocked"] = body.is_blocked
    if body.block_reason is not None:
        updates["block_reason"] = body.block_reason
    if body.reminder_at is not None:
        try:
            updates["reminder_at"] = datetime.fromisoformat(body.reminder_at)
        except ValueError:
            raise HTTPException(400, "Invalid datetime format")
    if body.status is not None:
        try:
            updates["status"] = LeadStatus(body.status)
        except ValueError:
            raise HTTPException(400, "Invalid status")

    if updates:
        await repo.update_lead(lead, **updates)
    return _lead_to_dict(lead)


@router.patch("/{lead_id}/status")
async def update_status(
    lead_id: int,
    body: UpdateStatusRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    repo = LeadRepository(db)
    lead = await repo.get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    from app.services.status_service import change_lead_status
    await change_lead_status(db, lead, body.status, changed_by="admin")
    await db.commit()
    return {"ok": True}


@router.get("/{lead_id}/status-history")
async def get_status_history(lead_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    from sqlalchemy import select
    from app.models import LeadStatusHistory
    result = await db.execute(
        select(LeadStatusHistory)
        .where(LeadStatusHistory.lead_id == lead_id)
        .order_by(LeadStatusHistory.created_at.desc())
    )
    return [
        {
            "id": h.id,
            "old_status": h.old_status,
            "new_status": h.new_status,
            "changed_by": h.changed_by,
            "created_at": h.created_at.isoformat(),
        }
        for h in result.scalars().all()
    ]


@router.post("/{lead_id}/analyze")
async def analyze(lead_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    lead_repo = LeadRepository(db)
    gpt_repo = GptSettingsRepository(db)

    lead = await lead_repo.get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    events = await lead_repo.get_lead_events(lead_id)
    gpt_settings = await gpt_repo.get_or_create()

    lead_data = {
        "name": lead.name,
        "city": lead.city,
        "need": lead.need,
        "status": lead.status.value if lead.status else None,
        "has_phone": bool(lead.phone),
        "events": [{"type": e.event_type.value, "data": e.event_data} for e in events[-20:]],
        # Qualification
        "budget": getattr(lead, "investment_budget_range", None),
        "funding_source": getattr(lead, "funding_source", None),
        "decision_stage": getattr(lead, "current_decision_stage", None),
        "urgency": getattr(lead, "urgency_level", None),
        "has_business_exp": getattr(lead, "has_business_experience", None),
        "deal_stage": getattr(lead, "deal_stage", None),
        # Behavioral
        "engagement_score": getattr(lead, "engagement_score", 0),
        "presentation_clicked": getattr(lead, "presentation_clicked", False),
        "finance_model_clicked": getattr(lead, "finance_model_clicked", False),
        "faq_views": getattr(lead, "faq_views_count", 0),
        "free_questions": getattr(lead, "free_questions_count", 0),
        "interests": {
            "investments": getattr(lead, "interest_investments", False),
            "revenue": getattr(lead, "interest_revenue", False),
            "payback": getattr(lead, "interest_payback", False),
            "territory": getattr(lead, "interest_territory", False),
            "risks": getattr(lead, "interest_risks", False),
            "royalty": getattr(lead, "interest_royalty", False),
        },
    }

    result = await analyze_lead(lead_data, gpt_settings.analysis_prompt)

    from app.models import LeadTemperature
    try:
        temp = LeadTemperature(result.get("lead_temperature", "cold"))
    except ValueError:
        temp = LeadTemperature.cold

    await lead_repo.update_lead(
        lead,
        engagement_score=result.get("engagement_score", 0),
        lead_temperature=temp,
        ai_summary=result.get("summary", ""),
        ai_recommended_action=result.get("recommended_action", ""),
    )
    return result


@router.get("/{lead_id}/events")
async def get_events(lead_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    repo = LeadRepository(db)
    events = await repo.get_lead_events(lead_id)
    return [
        {
            "id": e.id,
            "lead_id": e.lead_id,
            "event_type": e.event_type.value,
            "event_data": e.event_data,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]


def _lead_to_dict(lead) -> dict:
    def g(field, default=None):
        return getattr(lead, field, default)
    return {
        "id": lead.id,
        "name": lead.name,
        "city": lead.city,
        "need": lead.need,
        "phone": lead.phone,
        "status": lead.status.value if lead.status else "new",
        "engagement_score": lead.engagement_score,
        "lead_temperature": lead.lead_temperature.value if lead.lead_temperature else "cold",
        "ai_summary": lead.ai_summary,
        "ai_recommended_action": lead.ai_recommended_action,
        "ai_priority": g("ai_priority"),
        "ai_script_recommendation": g("ai_script_recommendation"),
        "call_slot": lead.call_slot,
        # UTM
        "utm_source": g("utm_source"),
        "utm_campaign": g("utm_campaign"),
        "utm_medium": g("utm_medium"),
        "utm_content": g("utm_content"),
        "utm_term": g("utm_term"),
        "ad_platform": g("ad_platform"),
        "first_touch_at": g("first_touch_at").isoformat() if g("first_touch_at") else None,
        # Manager
        "manager_notes": g("manager_notes"),
        "manager_assigned": g("manager_assigned"),
        "manager_first_contact_at": g("manager_first_contact_at").isoformat() if g("manager_first_contact_at") else None,
        "manager_contact_attempts": g("manager_contact_attempts", 0),
        "call_completed": g("call_completed", False),
        "deal_stage": g("deal_stage"),
        "deal_won": g("deal_won"),
        "loss_reason": g("loss_reason"),
        "reminder_at": lead.reminder_at.isoformat() if g("reminder_at") else None,
        "is_blocked": g("is_blocked", False),
        # Geography
        "region": g("region"),
        "country": g("country"),
        "population_bucket": g("population_bucket"),
        "planned_opening_city": g("planned_opening_city"),
        "has_location_already": g("has_location_already"),
        "urgency_level": g("urgency_level"),
        "desired_opening_date": g("desired_opening_date"),
        # Qualification
        "current_decision_stage": g("current_decision_stage"),
        "main_objection": g("main_objection"),
        "preferred_contact_method": g("preferred_contact_method"),
        "contact_source_type": g("contact_source_type"),
        "investment_budget_range": g("investment_budget_range"),
        "funding_source": g("funding_source"),
        "has_initial_capital": g("has_initial_capital"),
        # Profile
        "has_business_experience": g("has_business_experience"),
        "business_experience_type": g("business_experience_type"),
        "has_franchise_experience": g("has_franchise_experience"),
        "wants_passive_model": g("wants_passive_model"),
        "is_owner_operator_intent": g("is_owner_operator_intent"),
        # Drop-off
        "drop_off_step": g("drop_off_step"),
        "drop_off_at": g("drop_off_at").isoformat() if g("drop_off_at") else None,
        # Behavioral
        "messages_count": g("messages_count", 0),
        "free_questions_count": g("free_questions_count", 0),
        "faq_views_count": g("faq_views_count", 0),
        "touches_received_count": g("touches_received_count", 0),
        "session_count": g("session_count", 0),
        # Material clicks
        "presentation_clicked": g("presentation_clicked", False),
        "finance_model_clicked": g("finance_model_clicked", False),
        "about_clicked": g("about_clicked", False),
        "site_clicked": g("site_clicked", False),
        "youtube_clicked": g("youtube_clicked", False),
        "manager_clicked": g("manager_clicked", False),
        # FAQ
        "faq_categories_viewed": g("faq_categories_viewed"),
        "faq_questions_viewed": g("faq_questions_viewed"),
        "faq_financial_score": g("faq_financial_score", 0),
        "faq_legal_score": g("faq_legal_score", 0),
        "faq_launch_score": g("faq_launch_score", 0),
        "faq_risk_score": g("faq_risk_score", 0),
        # Interests
        "interest_investments": g("interest_investments", False),
        "interest_revenue": g("interest_revenue", False),
        "interest_launch": g("interest_launch", False),
        "interest_support": g("interest_support", False),
        "interest_territory": g("interest_territory", False),
        "interest_risks": g("interest_risks", False),
        "interest_payback": g("interest_payback", False),
        "interest_royalty": g("interest_royalty", False),
        "interest_construction": g("interest_construction", False),
        "interest_real_cases": g("interest_real_cases", False),
        "interest_financing": g("interest_financing", False),
        "interest_credit": g("interest_credit", False),
        "interest_exclusivity": g("interest_exclusivity", False),
        # AI scores
        "intent_score": g("intent_score", 0),
        "commercial_readiness_score": g("commercial_readiness_score", 0),
        # Timestamps
        "created_at": lead.created_at.isoformat(),
        "updated_at": lead.updated_at.isoformat(),
        "last_activity_at": g("last_activity_at", lead.updated_at).isoformat() if g("last_activity_at") or lead.updated_at else None,
        "username": lead.user.username if lead.user else None,
        "telegram_user_id": lead.user.telegram_user_id if lead.user else None,
    }


@router.patch("/{lead_id}/crm")
async def update_crm_fields(
    lead_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    """Update CRM/manager fields on a lead."""
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    CRM_FIELDS = [
        "manager_assigned", "manager_contact_attempts", "call_completed",
        "deal_stage", "deal_won", "loss_reason",
        "current_decision_stage", "main_objection", "preferred_contact_method",
        "investment_budget_range", "funding_source", "has_initial_capital",
        "has_business_experience", "business_experience_type", "has_franchise_experience",
        "wants_passive_model", "is_owner_operator_intent",
        "urgency_level", "planned_opening_city", "has_location_already",
        "region", "population_bucket",
    ]
    from datetime import datetime
    for field in CRM_FIELDS:
        if field in body:
            setattr(lead, field, body[field])
    if "manager_first_contact_at" not in [f for f in body] and body.get("call_completed") and not lead.manager_first_contact_at:
        lead.manager_first_contact_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}


@router.get("/{lead_id}/conversation")
async def get_conversation(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    """Get conversation log for a lead."""
    from sqlalchemy import select
    from app.models import ConversationLog
    result = await db.execute(
        select(ConversationLog).where(ConversationLog.lead_id == lead_id).order_by(ConversationLog.created_at.asc())
    )
    logs = result.scalars().all()
    return [
        {
            "id": l.id,
            "role": l.role.value,
            "text": l.text,
            "detected_intent": l.detected_intent,
            "sentiment": l.sentiment,
            "created_at": l.created_at.isoformat(),
        }
        for l in logs
    ]


@router.post("/{lead_id}/reset-chat")
async def reset_chat(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    """Archive all lead activity, reset lead to fresh state, clear FSM."""
    import json
    from sqlalchemy import select
    from app.models import (
        LeadNote, Task, LeadEvent, LeadStatusHistory,
        Broadcast, LeadArchive, BroadcastStatus,
    )
    from datetime import datetime

    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")

    # Load user
    user_result = await db.execute(select(User).where(User.id == lead.user_id))
    user = user_result.scalars().first()
    if not user:
        raise HTTPException(400, "No Telegram user associated")

    tg_id = user.telegram_user_id

    # ── 1. Collect snapshots ──────────────────────────────────────────────
    events_r = await db.execute(select(LeadEvent).where(LeadEvent.lead_id == lead_id))
    events = events_r.scalars().all()

    notes_r = await db.execute(select(LeadNote).where(LeadNote.lead_id == lead_id))
    notes = notes_r.scalars().all()

    tasks_r = await db.execute(select(Task).where(Task.lead_id == lead_id))
    tasks = tasks_r.scalars().all()

    history_r = await db.execute(select(LeadStatusHistory).where(LeadStatusHistory.lead_id == lead_id))
    history = history_r.scalars().all()

    broadcasts_r = await db.execute(select(Broadcast).where(
        Broadcast.filters.contains(str(lead_id))
    ))

    def lead_to_dict(l):
        return {
            "id": l.id, "name": l.name, "city": l.city, "need": l.need,
            "phone": l.phone, "status": l.status.value if l.status else None,
            "engagement_score": l.engagement_score,
            "utm_source": getattr(l, "utm_source", None),
            "investment_budget_range": getattr(l, "investment_budget_range", None),
            "current_decision_stage": getattr(l, "current_decision_stage", None),
            "funding_source": getattr(l, "funding_source", None),
            "urgency_level": getattr(l, "urgency_level", None),
            "has_business_experience": getattr(l, "has_business_experience", None),
            "deal_stage": getattr(l, "deal_stage", None),
            "created_at": l.created_at.isoformat(),
        }

    archive = LeadArchive(
        lead_id=lead_id,
        reason="chat_reset",
        lead_snapshot=json.dumps(lead_to_dict(lead), ensure_ascii=False),
        events_snapshot=json.dumps([
            {"type": e.event_type.value, "data": e.event_data, "at": e.created_at.isoformat()}
            for e in events
        ], ensure_ascii=False),
        notes_snapshot=json.dumps([
            {"content": n.content, "at": n.created_at.isoformat(),
             "remind_at": n.remind_at.isoformat() if n.remind_at else None}
            for n in notes
        ], ensure_ascii=False),
        tasks_snapshot=json.dumps([
            {"title": t.title, "status": t.status.value, "due_at": t.due_at.isoformat() if t.due_at else None}
            for t in tasks
        ], ensure_ascii=False),
        status_history_snapshot=json.dumps([
            {"old": h.old_status, "new": h.new_status, "at": h.created_at.isoformat()}
            for h in history
        ], ensure_ascii=False),
    )
    db.add(archive)

    # ── 2. Reset lead fields ──────────────────────────────────────────────
    RESET_FIELDS = [
        "name", "city", "need", "phone", "call_slot",
        "manager_notes", "reminder_at", "ai_summary", "ai_recommended_action",
        "ai_priority", "ai_script_recommendation", "ai_analyzed_at",
        "drop_off_step", "drop_off_at", "manager_assigned", "manager_first_contact_at",
        "deal_stage", "deal_won", "loss_reason", "main_objection",
        "investment_budget_range", "funding_source", "has_initial_capital",
        "current_decision_stage", "urgency_level", "has_business_experience",
        "business_experience_type", "has_franchise_experience",
        "wants_passive_model", "is_owner_operator_intent",
        "utm_source", "utm_campaign", "utm_medium", "utm_content",
        "first_touch_at", "faq_categories_viewed", "faq_questions_viewed",
    ]
    for field in RESET_FIELDS:
        if hasattr(lead, field):
            setattr(lead, field, None)

    # Reset counters and booleans
    RESET_BOOLS = [
        "presentation_clicked", "finance_model_clicked", "about_clicked",
        "site_clicked", "youtube_clicked", "manager_clicked", "is_blocked",
        "call_completed",
        "interest_investments", "interest_revenue", "interest_launch",
        "interest_support", "interest_territory", "interest_risks",
        "interest_payback", "interest_royalty", "interest_construction",
        "interest_real_cases", "interest_financing", "interest_credit",
        "interest_exclusivity",
    ]
    for field in RESET_BOOLS:
        if hasattr(lead, field):
            setattr(lead, field, False)

    RESET_INTS = [
        "engagement_score", "intent_score", "commercial_readiness_score",
        "messages_count", "free_questions_count", "faq_views_count",
        "touches_received_count", "session_count", "manager_contact_attempts",
        "faq_financial_score", "faq_legal_score", "faq_launch_score", "faq_risk_score",
    ]
    for field in RESET_INTS:
        if hasattr(lead, field):
            setattr(lead, field, 0)

    lead.status = LeadStatus.new
    from app.models import LeadTemperature
    lead.lead_temperature = LeadTemperature.cold
    lead.block_reason = None

    # ── 3. Clear Redis FSM ────────────────────────────────────────────────
    try:
        import redis.asyncio as aioredis
        from app.config import settings
        r = aioredis.from_url(settings.redis_url)
        await r.delete(f"flow_node:{tg_id}")
        await r.delete(f"qual_reminder:{tg_id}")
        for pattern in [f"fsm:{tg_id}:*", f"fsm:*:{tg_id}:*", f"aiogram_fsm:{tg_id}:*"]:
            keys = await r.keys(pattern)
            for k in keys:
                await r.delete(k)
        await r.aclose()
    except Exception as e:
        pass  # Don't fail if Redis error

    await db.commit()
    return {"ok": True, "archive_id": archive.id}

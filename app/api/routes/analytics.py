from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.api.routes.auth import verify_token
from app.repositories.lead_repo import LeadRepository
from app.services.ai.claude_service import generate_weekly_report, analyze_leads_batch
from app.models import Lead, LeadTemperature, LeadStatus

router = APIRouter()


class BatchAnalysisRequest(BaseModel):
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    segment: str = "all"


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    repo = LeadRepository(db)
    return await repo.get_stats()


@router.get("/daily")
async def get_daily(days: int = 7, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    result = []
    for i in range(days - 1, -1, -1):
        day_start = (datetime.utcnow() - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        count = await db.scalar(
            select(func.count(Lead.id)).where(
                Lead.created_at >= day_start, Lead.created_at < day_end
            )
        )
        result.append({"date": day_start.strftime("%d.%m"), "leads": count or 0})
    return result


@router.get("/status-distribution")
async def get_status_distribution(db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    status_colors = {
        "new": "#94a3b8", "form_started": "#60a5fa", "materials_sent": "#a78bfa",
        "faq_engaged": "#818cf8", "call_requested": "#fb923c",
        "cold": "#cbd5e1", "warm": "#fbbf24", "hot": "#f87171",
    }
    result = []
    for status in LeadStatus:
        count = await db.scalar(select(func.count(Lead.id)).where(Lead.status == status))
        result.append({"name": status.value, "value": count or 0, "color": status_colors.get(status.value, "#94a3b8")})
    return result


@router.post("/weekly-report")
async def weekly_report(db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    repo = LeadRepository(db)
    stats = await repo.get_stats()
    return await generate_weekly_report(stats)


@router.get("/behavioral-stats")
async def get_behavioral_stats(db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    """Stats on lead behavioral data collected by the bot."""
    from sqlalchemy import select, func, case
    from app.models import Lead

    total = await db.scalar(select(func.count(Lead.id))) or 0

    # Material clicks
    clicks = {}
    for field in ["presentation_clicked", "finance_model_clicked", "about_clicked",
                  "site_clicked", "youtube_clicked", "manager_clicked"]:
        count = await db.scalar(
            select(func.count(Lead.id)).where(getattr(Lead, field, None) == True)
        ) or 0
        clicks[field] = count

    # Interests
    interests = {}
    for field in ["interest_investments", "interest_revenue", "interest_launch",
                  "interest_support", "interest_territory", "interest_risks",
                  "interest_payback", "interest_royalty"]:
        count = await db.scalar(
            select(func.count(Lead.id)).where(getattr(Lead, field, None) == True)
        ) or 0
        interests[field] = count

    # Engagement buckets
    high_eng = await db.scalar(select(func.count(Lead.id)).where(Lead.engagement_score >= 70)) or 0
    mid_eng = await db.scalar(select(func.count(Lead.id)).where(Lead.engagement_score.between(30, 69))) or 0
    low_eng = await db.scalar(select(func.count(Lead.id)).where(Lead.engagement_score < 30)) or 0

    # UTM sources
    utm_result = await db.execute(
        select(Lead.utm_source, func.count(Lead.id).label("count"))
        .where(Lead.utm_source.isnot(None))
        .group_by(Lead.utm_source)
        .order_by(func.count(Lead.id).desc())
        .limit(8)
    )
    utm_data = [{"source": r.utm_source, "count": r.count} for r in utm_result]

    # Free questions stats
    asked_questions = await db.scalar(
        select(func.count(Lead.id)).where(Lead.free_questions_count > 0)
    ) or 0

    return {
        "total": total,
        "material_clicks": [
            {"name": "Презентация", "value": clicks["presentation_clicked"]},
            {"name": "Финмодель", "value": clicks["finance_model_clicked"]},
            {"name": "О нас", "value": clicks["about_clicked"]},
            {"name": "YouTube", "value": clicks["youtube_clicked"]},
            {"name": "Менеджер", "value": clicks["manager_clicked"]},
            {"name": "Сайт", "value": clicks["site_clicked"]},
        ],
        "interests": [
            {"name": "Инвестиции", "value": interests["interest_investments"]},
            {"name": "Доходность", "value": interests["interest_revenue"]},
            {"name": "Запуск", "value": interests["interest_launch"]},
            {"name": "Поддержка", "value": interests["interest_support"]},
            {"name": "Территория", "value": interests["interest_territory"]},
            {"name": "Риски", "value": interests["interest_risks"]},
            {"name": "Окупаемость", "value": interests["interest_payback"]},
            {"name": "Роялти", "value": interests["interest_royalty"]},
        ],
        "engagement_buckets": [
            {"name": "Высокий (70+)", "value": high_eng, "color": "#f87171"},
            {"name": "Средний (30-69)", "value": mid_eng, "color": "#fbbf24"},
            {"name": "Низкий (<30)", "value": low_eng, "color": "#475569"},
        ],
        "utm_sources": utm_data,
        "asked_questions": asked_questions,
        "asked_questions_pct": round(asked_questions / total * 100) if total else 0,
    }


@router.post("/batch-analysis")
async def batch_analysis(
    body: BatchAnalysisRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    """Глубокий GPT-анализ стека лидов за период."""
    from sqlalchemy.orm import selectinload
    query = select(Lead).options(selectinload(Lead.user), selectinload(Lead.events))

    if body.date_from:
        query = query.where(Lead.created_at >= datetime.fromisoformat(body.date_from))
    if body.date_to:
        query = query.where(Lead.created_at <= datetime.fromisoformat(body.date_to))

    if body.segment != "all":
        repo = LeadRepository(db)
        leads = await repo.get_leads_by_segment(body.segment)
    else:
        result = await db.execute(query.order_by(Lead.created_at.desc()).limit(100))
        leads = result.scalars().all()

    # Формируем данные для GPT
    leads_data = []
    for lead in leads:
        events_summary = {}
        for e in (lead.events or []):
            events_summary[e.event_type.value] = events_summary.get(e.event_type.value, 0) + 1

        leads_data.append({
            "id": lead.id,
            "name": lead.name,
            "city": lead.city,
            "need": lead.need,
            "has_phone": bool(lead.phone),
            "username": lead.user.username if lead.user else None,
            "status": lead.status.value if lead.status else "new",
            "temperature": lead.lead_temperature.value if lead.lead_temperature else "cold",
            "engagement_score": lead.engagement_score,
            "utm_source": getattr(lead, "utm_source", None),
            "utm_campaign": getattr(lead, "utm_campaign", None),
            "messages_count": getattr(lead, "messages_count", 0),
            "free_questions_count": getattr(lead, "free_questions_count", 0),
            "faq_views_count": getattr(lead, "faq_views_count", 0),
            "presentation_clicked": getattr(lead, "presentation_clicked", False),
            "finance_model_clicked": getattr(lead, "finance_model_clicked", False),
            "manager_clicked": getattr(lead, "manager_clicked", False),
            "call_slot": lead.call_slot,
            "interests": {
                "investments": getattr(lead, "interest_investments", False),
                "revenue": getattr(lead, "interest_revenue", False),
                "launch": getattr(lead, "interest_launch", False),
                "support": getattr(lead, "interest_support", False),
                "territory": getattr(lead, "interest_territory", False),
                "risks": getattr(lead, "interest_risks", False),
                "payback": getattr(lead, "interest_payback", False),
                "royalty": getattr(lead, "interest_royalty", False),
            },
            "events_summary": events_summary,
            "last_activity": lead.last_activity_at.isoformat() if getattr(lead, "last_activity_at", None) else None,
            "created_at": lead.created_at.isoformat(),
            "ai_summary": lead.ai_summary,
            # Qualification data from bot
            "qualification": {
                "budget": getattr(lead, "investment_budget_range", None),
                "funding_source": getattr(lead, "funding_source", None),
                "decision_stage": getattr(lead, "current_decision_stage", None),
                "urgency": getattr(lead, "urgency_level", None),
                "has_business_exp": getattr(lead, "has_business_experience", None),
                "business_exp_type": getattr(lead, "business_experience_type", None),
                "deal_stage": getattr(lead, "deal_stage", None),
                "loss_reason": getattr(lead, "loss_reason", None),
            },
        })

    period_label = f"{body.date_from or 'начало'} — {body.date_to or 'сейчас'}"
    analysis = await analyze_leads_batch(leads_data, period_label)
    analysis["leads_count"] = len(leads_data)

    # Сохраняем в историю
    try:
        import json
        from app.models import AIAnalysis
        record = AIAnalysis(
            date_from=body.date_from,
            date_to=body.date_to,
            leads_count=len(leads_data),
            result_json=json.dumps(analysis, ensure_ascii=False),
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        analysis["analysis_id"] = record.id
        analysis["saved_at"] = record.created_at.isoformat()
    except Exception as e:
        logger.warning(f"Failed to save analysis: {e}")

    return analysis


@router.get("/ai-history")
async def get_ai_history(db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    """Get list of saved AI analyses sorted by date desc."""
    from app.models import AIAnalysis
    import json
    result = await db.execute(
        select(AIAnalysis).order_by(AIAnalysis.created_at.desc()).limit(50)
    )
    analyses = result.scalars().all()
    return [
        {
            "id": a.id,
            "date_from": a.date_from,
            "date_to": a.date_to,
            "leads_count": a.leads_count,
            "created_at": a.created_at.isoformat(),
            "period_summary": json.loads(a.result_json).get("period_summary", ""),
            "result": json.loads(a.result_json),
        }
        for a in analyses
    ]



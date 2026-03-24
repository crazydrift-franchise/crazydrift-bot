from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Lead, LeadStatusHistory, LeadStatus, EventType
from app.services.notifications import notify_manager

STATUS_LABELS = {
    "new": "Новый",
    "form_started": "Начал форму",
    "materials_sent": "Получил материалы",
    "faq_engaged": "Изучает FAQ",
    "call_requested": "Запросил звонок",
    "cold": "Холодный",
    "warm": "Тёплый",
    "hot": "Горячий",
}

# Statuses that trigger notifications to manager
# materials_sent — handled by notify_phone_received (more detailed)
# call_requested — handled by notify_call_requested (more detailed)
NOTIFY_STATUSES = {
    "hot",
    "warm",
}


async def change_lead_status(
    db: AsyncSession,
    lead: Lead,
    new_status: str,
    changed_by: str = "bot",
    notify: bool = True,
):
    """Change lead status, log history, optionally notify manager."""
    old_status = lead.status.value if lead.status else None
    if old_status == new_status:
        return

    # Save history
    history = LeadStatusHistory(
        lead_id=lead.id,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
    )
    db.add(history)

    # Update lead
    try:
        lead.status = LeadStatus(new_status)
    except ValueError:
        return
    lead.updated_at = datetime.utcnow()

    # Log event
    from app.models import LeadEvent
    event = LeadEvent(
        lead_id=lead.id,
        event_type=EventType.status_change,
        event_data=f"Статус: {STATUS_LABELS.get(old_status, old_status)} → {STATUS_LABELS.get(new_status, new_status)}",
    )
    db.add(event)

    # Notify manager for important statuses
    if notify and new_status in NOTIFY_STATUSES:
        old_label = STATUS_LABELS.get(old_status, old_status or "—")
        new_label = STATUS_LABELS.get(new_status, new_status)
        lead_name = lead.name or f"Лид #{lead.id}"
        lead_link = f"https://panel-crazyfr.ru/leads/{lead.id}"
        await notify_manager(
            f"🔔 *Смена статуса лида*\n"
            f"Лид: {lead_name}\n"
            f"Город: {lead.city or '—'}\n"
            f"Телефон: {lead.phone or '—'}\n"
            f"{old_label} → *{new_label}*\n"
            f"[Открыть карточку]({lead_link})"
        )

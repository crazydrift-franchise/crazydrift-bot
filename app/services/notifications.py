import logging
from aiogram import Bot
from app.config import settings

logger = logging.getLogger(__name__)

_bot: Bot | None = None
PANEL_URL = "https://panel-crazyfr.ru"

BUDGET_LABELS = {"<3m": "до 3 млн", "3-5m": "3–5 млн", "5-10m": "5–10 млн", "10m+": "10+ млн", "no_answer": "не указал"}
STAGE_LABELS = {
    "investing": "Ищет инвестиции", "comparing": "Сравнивает ниши",
    "choosing": "Выбирает франшизу", "ready_call": "Готов к звонку",
    "ready_contract": "Готов к договору", "exploring": "Изучает",
}
FUNDING_LABELS = {
    "own": "Собственные", "credit": "Кредит", "investor": "Инвестор",
    "partner": "Партнёр", "hybrid": "Гибрид", "undecided": "Не определился",
}
URGENCY_LABELS = {
    "now": "В ближайшее время", "3m": "3 месяца",
    "6m": "6 месяцев", "year": "Год", "exploring": "Не определился",
}


def set_bot(bot: Bot):
    global _bot
    _bot = bot


async def notify_manager(text: str):
    if not _bot or not settings.manager_chat_id:
        return
    try:
        await _bot.send_message(
            chat_id=settings.manager_chat_id,
            text=text,
            disable_web_page_preview=False,
        )
    except Exception as e:
        logger.warning(f"Failed to notify manager: {e}")


def _lead_link(lead_id: int) -> str:
    return f"{PANEL_URL}/leads/{lead_id}"


def _fmt_phone(phone: str | None) -> str:
    if not phone:
        return "—"
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 11:
        return f"+{digits[0]} {digits[1:4]} {digits[4:7]} {digits[7:9]} {digits[9:11]}"
    return phone


def _utm_block(lead) -> str:
    lines = []
    for field, label in [
        ("utm_source", "utm_source"), ("utm_campaign", "utm_campaign"),
        ("utm_medium", "utm_medium"), ("utm_content", "utm_content"),
        ("utm_term", "utm_term"),
    ]:
        val = getattr(lead, field, None)
        if val:
            lines.append(f"{label}={val}")
    return "\n".join(lines)


def _username(lead) -> str:
    user = getattr(lead, "user", None)
    uname = getattr(user, "username", None) if user else None
    return f"@{uname}" if uname else "—"


# ── 1. Новый лид ──────────────────────────────────────────────────────────────
async def notify_new_lead(name: str, city: str | None, username: str | None,
                           lead_id: int | None = None, lead=None):
    lines = [
        "Новый лид",
        f"Логин: @{username}" if username else "Логин: —",
    ]
    if lead_id:
        lines.append(_lead_link(lead_id))
    await notify_manager("\n".join(l for l in lines if l))


# ── 2. Заполнил форму ─────────────────────────────────────────────────────────
async def notify_phone_received(name: str, phone: str, city: str | None,
                                 lead_id: int | None = None, lead=None):
    lines = [
        f"📋 Лид заполнил форму",
        f"Лид: #{lead_id or '—'}",
        f"Имя: {name or '—'}",
        f"Логин: {_username(lead) if lead else '—'}",
        f"Номер телефона: {_fmt_phone(phone)}",
        f"Город: {city or '—'}",
    ]
    if lead:
        budget = getattr(lead, "investment_budget_range", None)
        stage = getattr(lead, "current_decision_stage", None)
        funding = getattr(lead, "funding_source", None)
        if budget:
            lines.append(f"Бюджет: {BUDGET_LABELS.get(budget, budget)}")
        if stage:
            lines.append(f"На какой стадии: {STAGE_LABELS.get(stage, stage)}")
        if funding:
            lines.append(f"Источник финансов: {FUNDING_LABELS.get(funding, funding)}")
    if lead_id:
        lines.append(_lead_link(lead_id))
    await notify_manager("\n".join(l for l in lines if l))


# ── 3. Запросил звонок ────────────────────────────────────────────────────────
async def notify_call_requested(name: str, slot: str, phone: str | None,
                                 city: str | None = None, lead_id: int | None = None, lead=None):
    lines = [
        f"🔔 Лид запросил звонок",
        f"Лид: #{lead_id or '—'}",
        f"Имя: {name or '—'}",
        f"Логин: {_username(lead) if lead else '—'}",
        f"Номер телефона: {_fmt_phone(phone)}",
        f"Город: {city or '—'}",
    ]
    if lead:
        budget = getattr(lead, "investment_budget_range", None)
        stage = getattr(lead, "current_decision_stage", None)
        funding = getattr(lead, "funding_source", None)
        if budget:
            lines.append(f"Бюджет: {BUDGET_LABELS.get(budget, budget)}")
        if stage:
            lines.append(f"На какой стадии: {STAGE_LABELS.get(stage, stage)}")
        if funding:
            lines.append(f"Источник финансов: {FUNDING_LABELS.get(funding, funding)}")
    lines.append(f"Время для звонка: {slot}")
    if lead_id:
        lines.append(_lead_link(lead_id))
    await notify_manager("\n".join(l for l in lines if l))


# ── 4. Квалификация заполнена ─────────────────────────────────────────────────
async def notify_qualification(name: str, city: str | None, lead_id: int | None = None,
                                budget: str | None = None, funding: str | None = None,
                                urgency: str | None = None, has_exp: bool | None = None,
                                decision_stage: str | None = None, phone: str | None = None,
                                username: str | None = None):
    lines = [
        f"📋 Лид заполнил квалификацию",
        f"Лид: #{lead_id or '—'}",
        f"Имя: {name or '—'}",
        f"Логин: @{username}" if username else "Логин: —",
        f"Номер телефона: {_fmt_phone(phone)}",
        f"Город: {city or '—'}",
    ]
    if budget:
        lines.append(f"Бюджет: {BUDGET_LABELS.get(budget, budget)}")
    if decision_stage:
        lines.append(f"На какой стадии: {STAGE_LABELS.get(decision_stage, decision_stage)}")
    if funding:
        lines.append(f"Источник финансов: {FUNDING_LABELS.get(funding, funding)}")
    if has_exp is not None:
        lines.append(f"Опыт в бизнесе: {'есть' if has_exp else 'нет'}")
    if urgency:
        lines.append(f"Планирует запуск через: {URGENCY_LABELS.get(urgency, urgency)}")
    if lead_id:
        lines.append(_lead_link(lead_id))
    await notify_manager("\n".join(l for l in lines if l))


# ── Напоминание ───────────────────────────────────────────────────────────────
async def notify_reminder(name: str, lead_id: int, notes: str | None, city: str | None = None):
    lines = [
        f"⏰ Напоминание о лиде",
        f"Имя: {name or '—'}",
        f"Город: {city or '—'}",
        f"ID: #{lead_id}",
        f"Заметка: {notes or '—'}",
        _lead_link(lead_id),
    ]
    await notify_manager("\n".join(lines))


async def load_manager_chat_id():
    try:
        import redis.asyncio as aioredis
        from app.config import settings as _s
        r = aioredis.from_url(_s.redis_url)
        val = await r.get('manager_chat_id')
        if val:
            _s.manager_chat_id = int(val)
        await r.aclose()
    except Exception:
        pass

import logging
from aiogram import Bot
from app.config import settings
from app.models.bot2_models import AKUser, AKSignal, AKMessage

logger = logging.getLogger(__name__)

_bot: Bot | None = None

_SIGNAL_LABELS = {
    "tired_business":    "устал от бизнеса",
    "has_capital":       "есть свободный капитал",
    "wants_alternative": "ищет альтернативу",
    "asked_franchise":   "спросил про франшизу",
}


def set_bot(bot: Bot) -> None:
    global _bot
    _bot = bot


async def notify_ak_lead(
    user: AKUser,
    signals: list[AKSignal],
    last_messages: list[AKMessage],
    sections_visited: list[str],
) -> None:
    """Отправляет лид-карточку менеджеру CrazyDrift."""
    if not _bot or not settings.manager_chat_id:
        logger.warning("ak lead notify: bot or manager_chat_id not set")
        return

    signal_text = "\n".join(
        f"  • {_SIGNAL_LABELS.get(s.signal_type, s.signal_type)}"
        for s in signals
    ) or "  —"

    last_msgs_text = ""
    for m in last_messages[-5:]:
        prefix = "👤" if m.role == "user" else "🤖"
        last_msgs_text += f"{prefix} {m.text[:120]}\n"

    sections_text = ", ".join(sections_visited) if sections_visited else "—"

    business_info = []
    if user.business_type:
        business_info.append(f"Тип бизнеса: {user.business_type}")
    if user.employee_count:
        business_info.append(f"Сотрудников: {user.employee_count}")
    if user.city:
        business_info.append(f"Город: {user.city}")
    business_text = "\n".join(business_info) if business_info else "не указан"

    username_str = f"@{user.username}" if user.username else "нет username"

    text = (
        f"🔥 <b>ГОРЯЧИЙ ЛИД | Антикризисник → CrazyDrift</b>\n\n"
        f"👤 {user.first_name or 'Пользователь'} · {username_str}\n"
        f"🆔 TG ID: <code>{user.telegram_user_id}</code>\n"
        f"📅 В боте: {user.session_count} сессий"
        + (f" · 📡 {user.utm_source}" if user.utm_source else "")
        + "\n\n"
        f"🏢 <b>Бизнес</b>\n{business_text}\n\n"
        f"🌡 <b>Сигналы перехода</b>\n{signal_text}\n\n"
        f"🗂 <b>Разделы справочника</b>\n  {sections_text}\n\n"
        f"💬 <b>Последние сообщения</b>\n{last_msgs_text}"
        f"\n⚡ <b>Действие:</b> позвоните сегодня"
    )

    try:
        await _bot.send_message(
            chat_id=settings.manager_chat_id,
            text=text,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"ak lead notify failed: {e}")

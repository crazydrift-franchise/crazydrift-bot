"""
Квалификационный блок — запускается после получения номера телефона.
Задаёт 6 вопросов о цели, опыте, бюджете, стадии, источнике средств и сроках.
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from app.bot.states.lead_states import LeadForm
from app.database import AsyncSessionLocal
from app.repositories.lead_repo import LeadRepository

router = Router()
logger = logging.getLogger(__name__)

async def edit_or_delete(callback):
    """Remove keyboard from qualification question message."""
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


async def delete_bot_messages(bot, chat_id: int, message_ids: list[int]):
    """Delete multiple bot messages."""
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id, mid)
        except Exception:
            pass



PANEL_URL = "https://panel-crazyfr.ru"

# ─── Keyboards ────────────────────────────────────────────────────────────────

def qual_start_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ответить", callback_data="qual_start")],
        [InlineKeyboardButton(text="⏰ Отвечу позже", callback_data="qual_later_1h")],
    ])

def qual_experience_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, есть опыт", callback_data="qual_exp_yes")],
        [InlineKeyboardButton(text="❌ Нет опыта", callback_data="qual_exp_no")],
        [InlineKeyboardButton(text="Небольшой", callback_data="qual_exp_partial")],
    ])

def qual_budget_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="до 3 млн ₽", callback_data="qual_budget_<3m")],
        [InlineKeyboardButton(text="3–5 млн ₽", callback_data="qual_budget_3-5m")],
        [InlineKeyboardButton(text="5–10 млн ₽", callback_data="qual_budget_5-10m")],
        [InlineKeyboardButton(text="10+ млн ₽", callback_data="qual_budget_10m+")],
    ])

def qual_stage_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Ищу инвестиции", callback_data="qual_stage_investing")],
        [InlineKeyboardButton(text="⚖️ Сравниваю ниши", callback_data="qual_stage_comparing")],
        [InlineKeyboardButton(text="🎯 Выбираю франшизу", callback_data="qual_stage_choosing")],
        [InlineKeyboardButton(text="📊 Готов к презентации", callback_data="qual_stage_ready_call")],
        [InlineKeyboardButton(text="✍️ Готов к договору", callback_data="qual_stage_ready_contract")],
    ])

def qual_funding_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Собственные", callback_data="qual_fund_own")],
        [InlineKeyboardButton(text="🏦 Кредит", callback_data="qual_fund_credit")],
        [InlineKeyboardButton(text="🤝 Инвестор", callback_data="qual_fund_investor")],
        [InlineKeyboardButton(text="👥 Партнёр", callback_data="qual_fund_partner")],
        [InlineKeyboardButton(text="🔀 Гибрид", callback_data="qual_fund_hybrid")],
    ])

def qual_timing_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 В ближайшее время", callback_data="qual_time_now")],
        [InlineKeyboardButton(text="📅 Через 3 месяца", callback_data="qual_time_3m")],
        [InlineKeyboardButton(text="📅 Через 6 месяцев", callback_data="qual_time_6m")],
        [InlineKeyboardButton(text="📆 Через год", callback_data="qual_time_year")],
        [InlineKeyboardButton(text="🤔 Не определился", callback_data="qual_time_exploring")],
    ])

def remind_later_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, готов ответить", callback_data="qual_start")],
        [InlineKeyboardButton(text="⏰ Напомнить позже", callback_data="qual_remind_next")],
    ])

# ─── Qualification start ──────────────────────────────────────────────────────

async def start_qualification(bot, telegram_user_id: int, lead_state: FSMContext = None):
    """Send qualification invitation. Called after phone received."""
    text = (
        "Мы бы хотели познакомиться с Вами поближе 🤝\n\n"
        "Пожалуйста, ответьте на несколько коротких вопросов — это займёт не более 1 минуты "
        "и поможет нам подготовить для вас персональное предложение."
    )
    await bot.send_message(
        telegram_user_id,
        text,
        reply_markup=qual_start_keyboard(),
    )


# ─── Reminder system ─────────────────────────────────────────────────────────

async def schedule_qual_reminder(telegram_user_id: int, delay_hours: int, attempt: int):
    """Store reminder in Redis for later sending."""
    try:
        import redis.asyncio as aioredis
        import json
        from app.config import settings
        r = aioredis.from_url(settings.redis_url)
        from datetime import datetime, timedelta
        send_at = (datetime.utcnow() + timedelta(hours=delay_hours)).isoformat()
        key = f"qual_reminder:{telegram_user_id}"
        await r.setex(key, int(delay_hours * 3600 + 300), json.dumps({
            "telegram_user_id": telegram_user_id,
            "send_at": send_at,
            "attempt": attempt,
        }))
        await r.aclose()
    except Exception as e:
        logger.error(f"schedule_qual_reminder error: {e}")


# ─── Handlers ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "qual_start")
async def qual_begin(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await edit_or_delete(callback)
    await callback.message.answer(
        "1️⃣ *С какой целью хотите открыть бизнес?*\n\nНапишите в свободной форме:",
        parse_mode="Markdown",
    )
    await state.set_state(LeadForm.qual_goal)


@router.callback_query(F.data.in_({"qual_later_1h"}))
async def qual_later(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await edit_or_delete(callback)
    await schedule_qual_reminder(callback.from_user.id, 1, 1)
    await callback.message.answer("Хорошо! Напомню через 1 час 🕐")


@router.callback_query(F.data == "qual_remind_next")
async def qual_remind_next(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await edit_or_delete(callback)
    # Get current attempt from Redis
    try:
        import redis.asyncio as aioredis
        import json
        from app.config import settings
        r = aioredis.from_url(settings.redis_url)
        key = f"qual_reminder:{callback.from_user.id}"
        raw = await r.get(key)
        attempt = json.loads(raw).get("attempt", 1) if raw else 1
        await r.aclose()
    except Exception:
        attempt = 1

    if attempt == 1:
        await schedule_qual_reminder(callback.from_user.id, 6, 2)
        await callback.message.answer("Напомню через 6 часов ⏰")
    elif attempt == 2:
        await schedule_qual_reminder(callback.from_user.id, 24, 3)
        await callback.message.answer("Напомню завтра 📅")
    else:
        await callback.message.answer(
            "Хорошо, не буду беспокоить 🙏\n"
            "Когда будете готовы — просто напишите мне!"
        )


# ─── Question 1: Goal (free text) ─────────────────────────────────────────────

@router.message(LeadForm.qual_goal)
async def qual_goal_received(message: Message, state: FSMContext):
    goal = message.text.strip()
    await state.update_data(qual_goal=goal)

    async with AsyncSessionLocal() as db:
        repo = LeadRepository(db)
        lead = await repo.get_lead_by_telegram_id(message.from_user.id)
        if lead:
            lead.need = f"{lead.need or ''}\nЦель: {goal}".strip()
            await db.commit()

    await message.answer(
        "2️⃣ *Есть ли у вас опыт в бизнесе?*",
        parse_mode="Markdown",
        reply_markup=qual_experience_keyboard(),
    )
    await state.set_state(LeadForm.qual_experience)


# ─── Question 2: Experience ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("qual_exp_"))
async def qual_exp_received(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await edit_or_delete(callback)
    exp_map = {"qual_exp_yes": True, "qual_exp_no": False, "qual_exp_partial": True}
    exp_label_map = {"qual_exp_yes": "Да", "qual_exp_no": "Нет", "qual_exp_partial": "Небольшой"}
    has_exp = exp_map.get(callback.data)
    exp_label = exp_label_map.get(callback.data, "")
    await state.update_data(qual_experience=exp_label)

    async with AsyncSessionLocal() as db:
        repo = LeadRepository(db)
        lead = await repo.get_lead_by_telegram_id(callback.from_user.id)
        if lead:
            lead.has_business_experience = has_exp
            lead.business_experience_type = exp_label
            await db.commit()

    await callback.message.answer(
        "3️⃣ *Какой бюджет у вас есть на руках?*",
        parse_mode="Markdown",
        reply_markup=qual_budget_keyboard(),
    )
    await state.set_state(LeadForm.qual_budget)


# ─── Question 3: Budget ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("qual_budget_"))
async def qual_budget_received(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await edit_or_delete(callback)
    budget = callback.data.replace("qual_budget_", "")
    await state.update_data(qual_budget=budget)

    async with AsyncSessionLocal() as db:
        repo = LeadRepository(db)
        lead = await repo.get_lead_by_telegram_id(callback.from_user.id)
        if lead:
            lead.investment_budget_range = budget
            await db.commit()

    await callback.message.answer(
        "4️⃣ *На какой стадии вы сейчас находитесь?*",
        parse_mode="Markdown",
        reply_markup=qual_stage_keyboard(),
    )
    await state.set_state(LeadForm.qual_stage)


# ─── Question 4: Stage ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("qual_stage_"))
async def qual_stage_received(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await edit_or_delete(callback)
    stage = callback.data.replace("qual_stage_", "")
    await state.update_data(qual_stage=stage)

    async with AsyncSessionLocal() as db:
        repo = LeadRepository(db)
        lead = await repo.get_lead_by_telegram_id(callback.from_user.id)
        if lead:
            lead.current_decision_stage = stage
            await db.commit()

    # If ready for presentation — send materials
    if stage == "ready_call":
        await callback.message.answer(
            "Отлично! Выслал вам дополнительные материалы 📊\n\n"
            "Давайте продолжим знакомство — ещё пара вопросов."
        )
    elif stage == "ready_contract":
        # Trigger call slot selection
        from app.bot.keyboards.keyboards import call_slots_keyboard
        await callback.message.answer(
            "Прекрасно! Давайте назначим звонок с менеджером.\n\nВыберите удобное время:",
            reply_markup=call_slots_keyboard(),
        )
        return  # Skip remaining questions

    await callback.message.answer(
        "5️⃣ *Откуда планируете финансирование?*",
        parse_mode="Markdown",
        reply_markup=qual_funding_keyboard(),
    )
    await state.set_state(LeadForm.qual_funding)


# ─── Question 5: Funding ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("qual_fund_"))
async def qual_fund_received(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await edit_or_delete(callback)
    fund = callback.data.replace("qual_fund_", "")
    await state.update_data(qual_funding=fund)

    async with AsyncSessionLocal() as db:
        repo = LeadRepository(db)
        lead = await repo.get_lead_by_telegram_id(callback.from_user.id)
        if lead:
            lead.funding_source = fund
            await db.commit()

    await callback.message.answer(
        "6️⃣ *Когда планируете начать запуск бизнеса?*",
        parse_mode="Markdown",
        reply_markup=qual_timing_keyboard(),
    )
    await state.set_state(LeadForm.qual_timing)


# ─── Question 6: Timing ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("qual_time_"))
async def qual_timing_received(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await edit_or_delete(callback)
    timing = callback.data.replace("qual_time_", "")
    await state.update_data(qual_timing=timing)

    async with AsyncSessionLocal() as db:
        repo = LeadRepository(db)
        lead = await repo.get_lead_by_telegram_id(callback.from_user.id)
        if lead:
            lead.urgency_level = timing
            # Update decision stage based on timing
            if timing == "now" and not lead.current_decision_stage:
                lead.current_decision_stage = "ready_call"
            await db.commit()
            # Notify manager about completed qualification
            from app.services.notifications import notify_qualification
            user = getattr(lead, 'user', None)
            uname = getattr(user, 'username', None) if user else None
            await notify_qualification(
                name=lead.name or "—",
                city=lead.city,
                lead_id=lead.id,
                budget=lead.investment_budget_range,
                funding=lead.funding_source,
                urgency=timing,
                has_exp=lead.has_business_experience,
                decision_stage=lead.current_decision_stage,
                phone=lead.phone,
                username=uname,
            )

    data = await state.get_data()
    await callback.message.answer(
        "Спасибо за ответы! 🙏\n\n"
        "Наш менеджер свяжется с вами в ближайшее время с персональным предложением.\n\n"
        "Если хотите — можете ознакомиться с материалами или задать вопрос прямо сейчас 👇",
        reply_markup=__import__('app.bot.keyboards.keyboards', fromlist=['main_menu_keyboard']).main_menu_keyboard(),
    )
    await state.set_state(LeadForm.main_menu)

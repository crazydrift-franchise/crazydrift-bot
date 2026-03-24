from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart

from app.bot.states.lead_states import LeadForm
from app.bot.keyboards.keyboards import (
    start_keyboard, need_keyboard, phone_keyboard, remove_keyboard,
    materials_keyboard, main_menu_keyboard, call_slots_keyboard,
)
from app.database import AsyncSessionLocal
from app.repositories.lead_repo import LeadRepository
from app.models import LeadStatus, EventType
from app.services.notifications import notify_new_lead, notify_phone_received, notify_call_requested
from app.api.routes.outbound_webhook import fire_webhook

router = Router()


async def _remove_keyboard(callback):
    """Remove inline keyboard from previous message (don't delete the message)."""
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


# ── Interest detection ────────────────────────────────────────────────────────

INTEREST_KEYWORDS = {
    "interest_investments": ["инвест", "вложен", "капитал", "сколько стоит", "сумма"],
    "interest_revenue": ["выручк", "доход", "оборот", "прибыл", "заработ"],
    "interest_payback": ["окупаем", "окупится", "срок возврат", "roi"],
    "interest_territory": ["территори", "эксклюзив", "регион", "город", "другие в"],
    "interest_risks": ["риск", "опасн", "страш", "потеря", "убыток", "банкрот"],
    "interest_launch": ["запуск", "открыти", "старт", "начать", "с чего"],
    "interest_support": ["поддержк", "помощь", "сопровожден", "помогают"],
    "interest_royalty": ["роялт", "паушал", "взнос", "ежемесячн"],
    "interest_construction": ["ремонт", "строительств", "помещен", "площадь", "дизайн"],
    "interest_real_cases": ["примеры", "кейс", "действующ", "партнер", "другие"],
    "interest_financing": ["финансиров", "рассрочк", "лизинг"],
    "interest_credit": ["кредит", "займ", "банк", "ипотек"],
    "interest_exclusivity": ["эксклюзив", "один в городе", "только я", "права на город"],
}

INTENT_MAP = {
    "budget_question": ["сколько", "бюджет", "стоит", "цена", "инвест"],
    "roi": ["окупаем", "roi", "прибыл", "доход"],
    "territory": ["территори", "регион", "эксклюзив"],
    "support": ["поддержк", "помощь", "обучен"],
    "risk": ["риск", "страшно", "опасно"],
    "ready_to_call": ["позвони", "созвон", "свяжит", "договорим", "готов"],
    "comparison": ["другие", "конкурент", "сравнени", "vs "],
}

SENTIMENT_MAP = {
    "positive": ["отлично", "супер", "интересно", "нравится", "хочу", "готов", "давайте"],
    "negative": ["не хочу", "не надо", "отпишите", "не интересно", "дорого", "нет"],
    "curious": ["а что", "расскаж", "подробн", "как это", "почему", "зачем", "?"],
}


def detect_interests(text: str) -> dict:
    """Detect interest flags from message text."""
    text_lower = text.lower()
    result = {}
    for field, keywords in INTEREST_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            result[field] = True
    return result


def detect_intent(text: str) -> str | None:
    text_lower = text.lower()
    for intent, keywords in INTENT_MAP.items():
        if any(kw in text_lower for kw in keywords):
            return intent
    return "other"


def detect_sentiment(text: str) -> str:
    text_lower = text.lower()
    for sentiment, keywords in SENTIMENT_MAP.items():
        if any(kw in text_lower for kw in keywords):
            return sentiment
    return "neutral"


async def log_message(lead_id: int, role: str, text: str):
    """Save message to conversation_logs and update interest signals."""
    try:
        from app.models import ConversationLog, MessageRole
        async with AsyncSessionLocal() as db:
            log = ConversationLog(
                lead_id=lead_id,
                role=MessageRole(role),
                text=text[:2000],
                detected_intent=detect_intent(text) if role == "user" else None,
                sentiment=detect_sentiment(text) if role == "user" else None,
            )
            db.add(log)
            if role == "user":
                # Update interest flags on lead
                from sqlalchemy import select
                from app.models import Lead
                result = await db.execute(select(Lead).where(Lead.id == lead_id))
                lead = result.scalars().first()
                if lead:
                    interests = detect_interests(text)
                    for field, val in interests.items():
                        setattr(lead, field, val)
            await db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"log_message error: {e}")


async def track_drop_off(lead_id: int, step: str):
    """Record at which step the lead dropped off."""
    try:
        from app.models import Lead
        from datetime import datetime
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            result = await db.execute(select(Lead).where(Lead.id == lead_id))
            lead = result.scalars().first()
            if lead and not lead.drop_off_step:
                lead.drop_off_step = step
                lead.drop_off_at = datetime.utcnow()
                await db.commit()
    except Exception:
        pass

NEED_LABELS = {
    "need_investments": "Хочу понять инвестиции",
    "need_revenue": "Интересует доходность",
    "need_conditions": "Нужны условия франшизы",
    "need_launch": "Интересует запуск",
    "need_financial": "Хочу финансовую модель",
    "need_other": "Другое",
}


async def _check_blocked(telegram_user_id: int) -> bool:
    """Проверяем заблокирован ли лид."""
    async with AsyncSessionLocal() as db:
        repo = LeadRepository(db)
        lead = await repo.get_lead_by_telegram_id(telegram_user_id)
        return lead is not None and getattr(lead, "is_blocked", False)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    if await _check_blocked(message.from_user.id):
        return

    # Дедупликация — игнорируем повторный /start в течение 3 секунд
    from app.config import settings
    import redis.asyncio as aioredis
    try:
        r = aioredis.from_url(settings.redis_url)
        dedup_key = f"start_dedup:{message.from_user.id}"
        if await r.get(dedup_key):
            await r.aclose()
            return
        await r.setex(dedup_key, 3, "1")
        await r.aclose()
    except Exception:
        pass

    # Парсим UTM из payload: /start utm_source=ig__utm_campaign=stories
    utm_source = utm_campaign = utm_medium = None
    payload = message.text.split(" ", 1)[1] if " " in message.text else ""
    if payload:
        for part in payload.replace("__", "&").split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                if k == "utm_source": utm_source = v
                elif k == "utm_campaign": utm_campaign = v
                elif k == "utm_medium": utm_medium = v

    async with AsyncSessionLocal() as db:
        repo = LeadRepository(db)
        user, _ = await repo.get_or_create_user(
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        lead, created = await repo.get_or_create_lead(user)
        if created:
            await repo.add_event(lead.id, EventType.message, "Пользователь запустил бота (/start)")
            if utm_source or utm_campaign:
                await repo.update_lead(
                    lead,
                    utm_source=utm_source,
                    utm_campaign=utm_campaign,
                    utm_medium=utm_medium,
                )
        else:
            await repo.add_event(lead.id, EventType.message, "Повторный /start")
        already_filled = bool(lead.phone)
        lead_name = lead.name
        await db.commit()

    if created:
        await notify_new_lead(
            message.from_user.first_name or "—",
            None,
            message.from_user.username,
            lead_id=lead.id if lead else None,
            lead=lead,
        )
        await fire_webhook("new_lead", {
            "name": message.from_user.first_name,
            "username": message.from_user.username,
            "telegram_id": message.from_user.id,
        })
        # Создаём задачи для всех активных FAQ followup
        try:
            from sqlalchemy import select
            from app.models import FaqItem, Task, TaskPriority, TaskStatus
            from datetime import datetime, timedelta
            async with AsyncSessionLocal() as db2:
                faq_result = await db2.execute(
                    select(FaqItem).where(
                        FaqItem.followup_enabled == True,
                        FaqItem.followup_text.isnot(None),
                    )
                )
                faq_items = faq_result.scalars().all()
                for faq_item in faq_items:
                    due = datetime.utcnow() + timedelta(hours=faq_item.followup_delay_hours or 24)
                    task = Task(
                        title=f"📬 Дожим-рассылка: {faq_item.question[:60]}",
                        description=f"Плановая авто-рассылка из FAQ. Отправляется если лид не оставил телефон.\n\nТекст: {(faq_item.followup_text or '')[:200]}",
                        lead_id=lead.id,
                        due_at=due,
                        priority=TaskPriority.medium,
                        status=TaskStatus.todo,
                    )
                    db2.add(task)
                await db2.commit()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"FAQ task creation error: {e}")

    if already_filled:
        await state.set_state(LeadForm.main_menu)
        await message.answer(
            f"С возвращением, {lead_name or 'друг'}! 👋\n\nЧем могу помочь?",
            reply_markup=main_menu_keyboard(),
        )
        return

    await state.set_state(LeadForm.waiting_name)

    # Проверяем есть ли активная воронка в БД
    try:
        from app.services.flow_engine import handle_flow_start
        from aiogram import Bot
        bot = message.bot
        if bot and await handle_flow_start(bot, message.from_user.id):
            return  # Воронка из БД обработала — хардкод не нужен
    except Exception:
        pass

    await message.answer(
        "Добрый день! 👋\n\n"
        "Я виртуальный помощник по развитию сети развлекательных центров *CrazyDrift*.\n\n"
        "После заполнения короткой формы Вы получите:\n"
        "• Презентацию франшизы\n"
        "• Финансовую модель\n"
        "• Ответы на популярные вопросы",
        parse_mode="Markdown",
        reply_markup=start_keyboard(),
    )


@router.callback_query(F.data == "start_form")
async def start_form(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await _remove_keyboard(callback)
    await state.set_state(LeadForm.waiting_name)
    await callback.message.answer("Как Вас зовут? Укажите только имя.")


# ── Step 1: Name ─────────────────────────────────────────────────────────────

@router.message(LeadForm.waiting_name)
async def process_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2 or len(name) > 50:
        await message.answer("Пожалуйста, введите корректное имя (2-50 символов).")
        return

    await state.update_data(name=name)
    await state.set_state(LeadForm.waiting_city)

    async with AsyncSessionLocal() as db:
        repo = LeadRepository(db)
        lead = await repo.get_lead_by_telegram_id(message.from_user.id)
        if lead:
            from app.services.status_service import change_lead_status
            await change_lead_status(db, lead, LeadStatus.form_started.value, changed_by="bot", notify=False)
            await repo.update_lead(lead, name=name)
            await repo.add_event(lead.id, EventType.message, f"Имя: {name}")
            await log_message(lead.id, "user", name)
            # Clear drop_off if resuming
            if lead.drop_off_step == "name":
                lead.drop_off_step = None
        await db.commit()

    await message.answer(f"Приятно познакомиться, {name}! 😊\n\nВ каком городе планируете открытие бизнеса?")


# ── Step 2: City ─────────────────────────────────────────────────────────────

@router.message(LeadForm.waiting_city)
async def process_city(message: Message, state: FSMContext):
    city = message.text.strip()
    if len(city) < 2 or len(city) > 100:
        await message.answer("Пожалуйста, введите название города.")
        return

    await state.update_data(city=city)
    await state.set_state(LeadForm.waiting_need)

    async with AsyncSessionLocal() as db:
        repo = LeadRepository(db)
        lead = await repo.get_lead_by_telegram_id(message.from_user.id)
        if lead:
            await repo.update_lead(lead, city=city)
            await repo.add_event(lead.id, EventType.message, f"Город: {city}")
        await db.commit()

    await message.answer(
        "Что для Вас важно при принятии решения?",
        reply_markup=need_keyboard(),
    )


# ── Step 3: Need ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("need_"))
async def process_need(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await _remove_keyboard(callback)
    need_label = NEED_LABELS.get(callback.data, "Другое")
    await state.update_data(need=need_label)
    await state.set_state(LeadForm.waiting_phone)

    async with AsyncSessionLocal() as db:
        repo = LeadRepository(db)
        lead = await repo.get_lead_by_telegram_id(callback.from_user.id)
        if lead:
            await repo.update_lead(lead, need=need_label)
            await repo.add_event(lead.id, EventType.click, f"Интерес: {need_label}")
        await db.commit()

    await callback.message.answer(
        "Для отправки материалов укажите Ваш номер телефона.\n\n"
        "Нажмите кнопку ниже или введите номер вручную:",
        reply_markup=phone_keyboard(),
    )


# ── Step 4: Phone ─────────────────────────────────────────────────────────────

@router.message(LeadForm.waiting_phone, F.contact)
async def process_phone_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    await _save_phone_and_send_materials(message, state, phone)


@router.message(LeadForm.waiting_phone)
async def process_phone_text(message: Message, state: FSMContext):
    import re
    raw = message.text.strip()
    phone = re.sub(r'[\s\-\(\)]', '', raw)
    if not phone.startswith('+'):
        phone = '+' + phone
    digits = phone[1:]
    if not digits.isdigit() or len(digits) < 10 or len(digits) > 15:
        await message.answer(
            "Введите корректный номер телефона.\n"
            "Пример: +79991234567"
        )
        return
    await _save_phone_and_send_materials(message, state, phone)


async def _save_phone_and_send_materials(message: Message, state: FSMContext, phone: str):
    masked = phone[:4] + "***" + phone[-4:]

    async with AsyncSessionLocal() as db:
        repo = LeadRepository(db)
        from sqlalchemy import select
        from app.models import Lead as LeadModel, User
        lead_obj = await repo.get_lead_by_telegram_id(message.from_user.id)
        lead = lead_obj
        if lead:
            # Load user explicitly for notifications
            user_result = await db.execute(select(User).where(User.id == lead.user_id))
            lead.user = user_result.scalars().first()
            from app.services.status_service import change_lead_status
            await change_lead_status(db, lead, LeadStatus.materials_sent.value, changed_by="bot")
            await repo.update_lead(lead, phone=phone)
            await repo.add_event(lead.id, EventType.message, f"Телефон: {masked}")
            lead_name = lead.name
            lead_city = lead.city
        await db.commit()

    await state.set_state(LeadForm.main_menu)
    await notify_phone_received(lead_name or "—", phone, lead_city, lead_id=lead.id if lead else None, lead=lead)
    await fire_webhook("phone_received", {"name": lead_name, "phone": phone, "city": lead_city})
    await message.answer(
        "Спасибо, за проявленный интерес к франшизе CrazyDrift! 🎉\n"
        "Высылаю материалы для ознакомления:",
        reply_markup=remove_keyboard(),
    )
    await message.answer(
        "Вот всё необходимое для знакомства с нашей франшизой:",
        reply_markup=materials_keyboard(),
    )
    await message.answer(
        "───────────────────\n\n"
        "Мы бы хотели познакомиться с Вами 🤝\n\n"
        "Пожалуйста, ответьте на несколько коротких вопросов — это поможет нам "
        "подготовить персональное предложение именно для вас:",
        reply_markup=__import__('app.bot.handlers.qualification_handler',
                                fromlist=['qual_start_keyboard']).qual_start_keyboard(),
    )


# ── Main menu ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "back_menu")
@router.callback_query(F.data == "menu_materials")
async def menu_materials(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await _remove_keyboard(callback)
    await callback.message.answer(
        "Материалы по франшизе CrazyDrift:",
        reply_markup=materials_keyboard(),
    )
    await callback.message.answer("Чем ещё могу помочь?", reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "menu_manager")
async def menu_manager(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await _remove_keyboard(callback)
    from app.config import settings
    async with AsyncSessionLocal() as db:
        repo = LeadRepository(db)
        lead = await repo.get_lead_by_telegram_id(callback.from_user.id)
        if lead:
            await repo.add_event(lead.id, EventType.click, "Запросил связь с менеджером")
        await db.commit()
    await callback.message.answer(
        f"Наш менеджер готов ответить на все вопросы: {settings.materials_manager_url}"
    )


@router.callback_query(F.data == "menu_call")
async def menu_call(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await _remove_keyboard(callback)
    async with AsyncSessionLocal() as db:
        repo = LeadRepository(db)
        lead = await repo.get_lead_by_telegram_id(callback.from_user.id)
        if lead:
            await repo.add_event(lead.id, EventType.click, "Нажал «Записаться на звонок»")
        await db.commit()
    await callback.message.answer(
        "Когда Вам удобно принять звонок?",
        reply_markup=call_slots_keyboard(),
    )


@router.callback_query(F.data.startswith("call_"))
async def process_call_slot(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await _remove_keyboard(callback)
    slots = {
        "call_now": "В ближайшее время",
        "call_09": "09:00–13:00",
        "call_13": "13:00–17:00",
        "call_17": "17:00–21:00",
        "call_later": "Пока не готов",
    }
    slot = slots.get(callback.data, "")
    lead_name = lead_phone = lead_city = None

    async with AsyncSessionLocal() as db:
        repo = LeadRepository(db)
        lead = await repo.get_lead_by_telegram_id(callback.from_user.id)
        if lead:
            # Load user explicitly
            from sqlalchemy import select
            from app.models import User
            user_result = await db.execute(select(User).where(User.id == lead.user_id))
            lead.user = user_result.scalars().first()
            if slot != "Пока не готов":
                from app.services.status_service import change_lead_status
                await change_lead_status(db, lead, LeadStatus.call_requested.value, changed_by="bot")
                await repo.update_lead(lead, call_slot=slot)
            await repo.add_event(lead.id, EventType.click, f"Слот звонка: {slot}")
            lead_name = lead.name
            lead_phone = lead.phone
            lead_city = lead.city
        await db.commit()

    if slot == "Пока не готов":
        await callback.message.answer(
            "Понял! Когда будете готовы — нажмите «Записаться на звонок» в меню.",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await notify_call_requested(lead_name or "—", slot, lead_phone, city=lead_city, lead_id=lead.id if lead else None, lead=lead)
        await callback.message.answer(
            f"✅ Записал! Менеджер свяжется с Вами в {slot}.\n\n"
            "Если возникнут вопросы — я здесь 👇",
            reply_markup=main_menu_keyboard(),
        )


# ── Material click tracking ───────────────────────────────────────────────────

MATERIAL_MAP = {
    "mat_about":        ("about_clicked",        "materials_about_url",        "О нас"),
    "mat_presentation": ("presentation_clicked",  "materials_presentation_url", "Презентация"),
    "mat_finance":      ("finance_model_clicked", "materials_financial_url",    "Финансовая модель"),
    "mat_site":         ("site_clicked",          "materials_site_url",         "Сайт"),
    "mat_youtube":      ("youtube_clicked",       "materials_youtube_url",      "YouTube"),
    "mat_manager":      ("manager_clicked",       "materials_manager_url",      "Связь с менеджером"),
}


@router.callback_query(F.data.startswith("mat_"))
async def track_material_click(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await _remove_keyboard(callback)
    field, url_attr, label = MATERIAL_MAP.get(callback.data, (None, None, None))
    if not field:
        return

    from app.config import settings
    url = getattr(settings, url_attr, "#")

    async with AsyncSessionLocal() as db:
        repo = LeadRepository(db)
        lead = await repo.get_lead_by_telegram_id(callback.from_user.id)
        if lead:
            await repo.update_lead(lead, **{field: True}, last_activity_at=__import__("datetime").datetime.utcnow())
            await repo.add_event(lead.id, EventType.click, f"Материал: {label}")
        await db.commit()

    await callback.message.answer(f"Открываю: {url}")


# ── Flow Engine callbacks ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("flow_btn:"))
async def handle_flow_button(callback: CallbackQuery, state: FSMContext):
    """Handle button press from dynamic flow."""
    await callback.answer()
    await _remove_keyboard(callback)
    try:
        parts = callback.data.split(":")
        node_id = parts[1]
        btn_id = parts[2]
        from app.services.flow_engine import handle_flow_callback
        await handle_flow_callback(callback.bot, callback.from_user.id, node_id, btn_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"flow_btn error: {e}")


# ── FAQ GPT Follow-up button ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("faq_gpt:"))
async def handle_faq_gpt_button(callback: CallbackQuery, state: FSMContext):
    """Handle GPT answer button from FAQ followup."""
    await callback.answer()
    await _remove_keyboard(callback)
    try:
        parts = callback.data.split(":")
        faq_item_id = int(parts[1])
        btn_id = parts[2] if len(parts) > 2 else ""

        await callback.message.answer("🤔 Готовлю развёрнутый ответ...", parse_mode="Markdown")

        async with AsyncSessionLocal() as db:
            from app.models import FaqItem
            item = await db.get(FaqItem, faq_item_id)
            if not item:
                return
            import json
            buttons = json.loads(item.followup_buttons) if item.followup_buttons else []
            btn = next((b for b in buttons if b.get("id") == btn_id), None)
            hint = btn.get("value", "") if btn else ""
            question = f"{item.question}. {hint}".strip() if hint else item.question

        from app.services.ai.claude_service import get_gpt_answer
        try:
            answer = await get_gpt_answer(question)
        except Exception:
            answer = item.answer if item else "Не удалось получить ответ. Обратитесь к менеджеру."

        await callback.message.answer(answer, parse_mode="Markdown")
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"faq_gpt error: {e}")
        await callback.message.answer("Произошла ошибка. Пожалуйста, свяжитесь с менеджером.")

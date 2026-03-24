from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.bot.states.lead_states import LeadForm
from app.bot.keyboards.keyboards import (
    faq_categories_keyboard, faq_items_keyboard, after_faq_keyboard, main_menu_keyboard
)
from app.database import AsyncSessionLocal
from app.repositories.lead_repo import LeadRepository
from app.repositories.faq_repo import FaqRepository, KnowledgeRepository, GptSettingsRepository
from app.services.ai.claude_service import ask_bot
from app.models import EventType, LeadStatus

router = Router()


# ── FAQ ───────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu_faq")
async def show_faq_categories(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    async with AsyncSessionLocal() as db:
        faq_repo = FaqRepository(db)
        categories = await faq_repo.get_active_categories()

        lead_repo = LeadRepository(db)
        lead = await lead_repo.get_lead_by_telegram_id(callback.from_user.id)
        if lead:
            await lead_repo.update_lead(lead, status=LeadStatus.faq_engaged)
            await lead_repo.add_event(lead.id, EventType.faq, "Открыл раздел FAQ")
        await db.commit()

    if not categories:
        await callback.message.answer("FAQ пока пуст. Задайте вопрос текстом — я отвечу!")
        return

    await state.set_state(LeadForm.faq_category)
    await callback.message.answer(
        "Выберите категорию вопросов:",
        reply_markup=faq_categories_keyboard(categories),
    )


@router.callback_query(F.data.startswith("faq_cat_"))
async def show_faq_items(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    category_id = int(callback.data.split("_")[-1])

    async with AsyncSessionLocal() as db:
        faq_repo = FaqRepository(db)
        items = await faq_repo.get_active_items_by_category(category_id)

        lead_repo = LeadRepository(db)
        lead = await lead_repo.get_lead_by_telegram_id(callback.from_user.id)
        if lead:
            await lead_repo.add_event(lead.id, EventType.faq, f"Открыл категорию FAQ id={category_id}")
        await db.commit()

    if not items:
        await callback.message.answer("В этой категории пока нет вопросов.")
        return

    await state.set_state(LeadForm.faq_item)
    await callback.message.answer(
        "Выберите вопрос:",
        reply_markup=faq_items_keyboard(items, category_id),
    )


@router.callback_query(F.data.startswith("faq_item_"))
async def show_faq_answer(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    item_id = int(callback.data.split("_")[-1])

    async with AsyncSessionLocal() as db:
        faq_repo = FaqRepository(db)
        item = await faq_repo.get_item_by_id(item_id)

        lead_repo = LeadRepository(db)
        lead = await lead_repo.get_lead_by_telegram_id(callback.from_user.id)
        if lead and item:
            await lead_repo.add_event(
                lead.id, EventType.faq,
                f"Вопрос: {item.question[:80]}"
            )
        await db.commit()

    if not item:
        await callback.message.answer("Вопрос не найден.")
        return

    await callback.message.answer(
        f"❓ *{item.question}*\n\n{item.answer}",
        parse_mode="Markdown",
        reply_markup=after_faq_keyboard(),
    )


# ── Free text → AI ────────────────────────────────────────────────────────────

@router.message(F.text)
async def handle_free_text(message: Message, state: FSMContext):
    """Catch all text messages not caught by other handlers → send to Claude."""
    current_state = await state.get_state()

    if current_state in [LeadForm.waiting_name, LeadForm.waiting_city,
                          LeadForm.waiting_phone, LeadForm.waiting_need,
                          LeadForm.qual_goal]:
        return

    user_text = message.text.strip()
    if len(user_text) < 2:
        return

    # Проверка блокировки
    async with AsyncSessionLocal() as db:
        repo = LeadRepository(db)
        lead = await repo.get_lead_by_telegram_id(message.from_user.id)
        if lead and getattr(lead, "is_blocked", False):
            return
        await db.commit()

    # Show typing indicator
    await message.bot.send_chat_action(message.chat.id, "typing")

    # Автодетект интересов из текста
    text_lower = user_text.lower()
    interest_updates = {}
    if any(w in text_lower for w in ["инвестиц", "вложен", "капитал"]): interest_updates["interest_investments"] = True
    if any(w in text_lower for w in ["доход", "прибыл", "выручк", "заработ"]): interest_updates["interest_revenue"] = True
    if any(w in text_lower for w in ["запуск", "открыт", "старт"]): interest_updates["interest_launch"] = True
    if any(w in text_lower for w in ["поддержк", "помощ", "сопровожд"]): interest_updates["interest_support"] = True
    if any(w in text_lower for w in ["территори", "эксклюзив", "регион", "город"]): interest_updates["interest_territory"] = True
    if any(w in text_lower for w in ["риск", "опасн", "банкрот", "убыток"]): interest_updates["interest_risks"] = True
    if any(w in text_lower for w in ["окупаем", "возврат", "roi"]): interest_updates["interest_payback"] = True
    if any(w in text_lower for w in ["роялт", "паушал", "взнос", "процент"]): interest_updates["interest_royalty"] = True

    async with AsyncSessionLocal() as db:
        kb_repo = KnowledgeRepository(db)
        gpt_repo = GptSettingsRepository(db)
        lead_repo = LeadRepository(db)

        knowledge = await kb_repo.get_as_text()
        gpt_settings = await gpt_repo.get_or_create()

        lead = await lead_repo.get_lead_by_telegram_id(message.from_user.id)
        if lead:
            import datetime as dt
            update_kwargs = {
                "last_activity_at": dt.datetime.utcnow(),
                "messages_count": (lead.messages_count or 0) + 1,
                "free_questions_count": (lead.free_questions_count or 0) + 1,
                **interest_updates,
            }
            await lead_repo.update_lead(lead, **update_kwargs)
            await lead_repo.add_event(lead.id, EventType.message, f"Вопрос: {user_text[:200]}")

        await db.commit()

    # Call Claude
    answer = await ask_bot(user_text, gpt_settings.system_prompt, knowledge)

    async with AsyncSessionLocal() as db:
        lead_repo = LeadRepository(db)
        lead = await lead_repo.get_lead_by_telegram_id(message.from_user.id)
        if lead:
            await lead_repo.add_event(lead.id, EventType.gpt_reply, f"AI: {answer[:200]}")
        await db.commit()

    await message.answer(answer, reply_markup=main_menu_keyboard())

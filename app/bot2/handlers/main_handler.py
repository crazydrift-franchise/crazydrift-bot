import asyncio
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart

from app.database import AsyncSessionLocal
from app.bot2.states.states import AKBotForm
from app.bot2.keyboards.keyboards import (
    main_menu_keyboard,
    playbook_keyboard,
    back_menu_keyboard,
    cd_offer_keyboard,
    cd_contact_keyboard,
)
from app.repositories.bot2_repo import AKBotRepository
from app.services.ai.antikrizis_service import get_antikrizis_advice, detect_transition_signals
from app.services import bot2_notifications

logger = logging.getLogger(__name__)
router = Router()

# ── Плейбуки ──────────────────────────────────────────────────────────────────

PLAYBOOKS: dict[str, dict] = {
    "revenue_drop": {
        "emoji": "📉", "title": "Упала выручка",
        "steps": [
            ("Сегодня",    "Зафиксируйте точку безубыточности — минимальная сумма в месяц, чтобы не уходить в минус. Запишите цифру."),
            ("2–3 дня",    "Найдите топ-3 источника выручки. Решите: масштабировать прибыльные или отрезать убыточные направления."),
            ("1 неделя",   "Позвоните 10 лучшим клиентам. Спросите напрямую: что изменилось, почему стали меньше покупать."),
            ("2 недели",   "Запустите возврат спящих клиентов — акция или персональное предложение. Это дешевле привлечения новых."),
            ("1 месяц",    "Пересмотрите ассортимент. 20% позиций дают 80% дохода — оставьте только их."),
        ],
    },
    "rent_problems": {
        "emoji": "🏢", "title": "Проблемы с арендой",
        "steps": [
            ("Сегодня",    "Свяжитесь с арендодателем первыми — не ждите требования. Это сигнал ответственности и снижает напряжение."),
            ("2 дня",      "Подготовьте данные: падение выручки в %, срок работы, перспективы. Это аргументы для переговоров."),
            ("3–5 дней",   "Предложите конкретную схему: отсрочка 1–2 месяца + частичная оплата + возврат долга к дате Х."),
            ("1 неделя",   "Если отказывают — предложите субаренду части площади или переход на % от выручки."),
            ("2 недели",   "Изучите 2–3 альтернативные локации. Реальная альтернатива — сильный аргумент на переговорах."),
        ],
    },
    "personnel": {
        "emoji": "👥", "title": "Персонал в кризис",
        "steps": [
            ("Сегодня",    "Разделите команду на три группы: незаменимые, полезные, замещаемые. Честно, без эмоций."),
            ("3 дня",      "Поговорите с ключевыми людьми индивидуально. Люди терпят трудности, когда понимают причины."),
            ("1 неделя",   "Для снижения затрат: неполная ставка, совмещение должностей, временный перевод на сдельную оплату."),
            ("2 недели",   "Оформите всё документально: допсоглашения, приказы. Нарушение ТК в кризис — дополнительный удар."),
            ("1 месяц",    "Предложите лучшим нематериальную мотивацию: гибкий график, перспективы роста, доля в успехе."),
        ],
    },
    "debts": {
        "emoji": "💳", "title": "Долги и кредиторы",
        "steps": [
            ("Сегодня",    "Составьте полный список долгов: кредиторы, суммы, сроки, проценты. Видеть картину целиком — первый шаг."),
            ("3 дня",      "Приоритеты: налоги и зарплата — первые, аренда и поставщики — вторые, банки — третьи."),
            ("1 неделя",   "Обратитесь в банк первыми. Запросите кредитные каникулы или реструктуризацию — им выгоднее перенос, чем дефолт."),
            ("2 недели",   "По поставщикам — предложите частичную оплату с графиком. Большинство согласятся лучше, чем получить ноль."),
            ("1 месяц",    "Изучите госпрограммы поддержки МСП: субсидии, льготные кредиты, налоговые отсрочки."),
        ],
    },
    "suppliers": {
        "emoji": "📦", "title": "Поставщики подняли цены",
        "steps": [
            ("Сегодня",    "Посчитайте: на сколько вырастет ваша себестоимость. Критично или терпимо — разные решения."),
            ("3 дня",      "Попросите поставщика объяснить причину роста. Иногда можно зафиксировать цену договором на квартал."),
            ("1 неделя",   "Найдите 2–3 альтернативных поставщика. Даже если не переключитесь — это аргумент на переговорах."),
            ("2 недели",   "Рассмотрите совместные закупки с другими предпринимателями (клубы, ассоциации МСП)."),
            ("1 месяц",    "Пересмотрите ассортимент: уберите позиции с низкой маржой, поднимите цены на топовые."),
        ],
    },
    "no_clients": {
        "emoji": "🎯", "title": "Нет новых клиентов",
        "steps": [
            ("Сегодня",    "Посмотрите на тех, кто уже был у вас. Существующая база — дешевле и горячее, чем холодная реклама."),
            ("3 дня",      "Запустите реферальную программу: клиент приводит друга → получает бонус. Работает в любом бизнесе."),
            ("1 неделя",   "Обновите карточки на Яндекс.Картах и 2ГИС: фото, цены, акции. Бесплатно и даёт клиентов."),
            ("2 недели",   "Договоритесь о партнёрстве с соседними неконкурирующими бизнесами. Обмен аудиторией стоит 0 ₽."),
            ("1 месяц",    "Запустите тестовый платный канал с минимальным бюджетом (3–5 тыс. ₽). Проверьте гипотезу."),
        ],
    },
    "no_salary": {
        "emoji": "💰", "title": "Нечем платить зарплату",
        "steps": [
            ("Сегодня",    "Поговорите с командой честно и первыми. Молчание хуже правды. Назовите конкретные сроки."),
            ("2 дня",      "Изучите краткосрочные варианты: овердрафт в банке, займ у партнёров, факторинг дебиторки."),
            ("3 дня",      "Проверьте дебиторку: кто должен вам прямо сейчас? Ускорьте получение этих денег."),
            ("1 неделя",   "Приоритет выплат: НДФЛ и страховые взносы — обязательны. Остальное — по договорённости."),
            ("2 недели",   "Оформите задержку официально с конкретной датой выплаты. Это снижает правовые риски."),
        ],
    },
    "change_direction": {
        "emoji": "🔄", "title": "Думаю сменить направление",
        "steps": [
            ("Первый шаг", "Честно ответьте: вы устали от ниши или от конкретных проблем? Усталость от проблем — решаемо. От ниши — другой разговор."),
            ("1 неделя",   "Составьте список: что в текущем бизнесе работает и что вы умеете. Это активы, которые можно перенести."),
            ("2 недели",   "Изучите 3–5 смежных направлений. Сделайте минимальный MVP или одну консультацию в каждом."),
            ("1 месяц",    "Посчитайте выход: сколько нужно для закрытия текущего бизнеса — долги, обязательства, команда."),
            ("Следующий шаг", "Рассмотрите готовые бизнес-модели с подтверждённой экономикой — это снижает риск при смене направления."),
        ],
    },
    "start_from_zero": {
        "emoji": "🆘", "title": "Всё плохо — с чего начать",
        "steps": [
            ("Прямо сейчас", "Остановитесь. Запишите три самые горящие проблемы. Не больше трёх. Всё сразу не решается."),
            ("Сегодня",    "Посчитайте: сколько денег осталось и на сколько дней хватит при нулевой выручке. Это ваш горизонт."),
            ("3 дня",      "До 14 дней — режим выживания (урезать всё). 30–60 дней — режим оптимизации. Разная тактика."),
            ("1 неделя",   "Одно действие для каждой из трёх проблем. Не идеальное — просто первый шаг. Движение лечит панику."),
            ("2 недели",   "Найдите одного человека, который прошёл через похожее. Разговор с практиком стоит любой статьи."),
        ],
    },
}

_SECTION_TITLES = {k: f"{v['emoji']} {v['title']}" for k, v in PLAYBOOKS.items()}

_CD_OFFER_TEXT = (
    "💡 <b>Есть одна мысль...</b>\n\n"
    "Судя по нашему разговору, вы думаете о смене направления или защите капитала.\n\n"
    "Есть проверенная модель готового бизнеса в сфере развлечений — "
    "<b>CrazyDrift</b>. Сеть работает в нескольких городах России. "
    "Возврат инвестиций — 18–24 месяца.\n\n"
    "Хотите узнать детали?"
)

_CD_CONFIRMED_TEXT = (
    "Отлично! Наш менеджер свяжется с вами в ближайшее время.\n\n"
    "Он ответит на все вопросы о франшизе и расскажет об условиях входа.\n\n"
    "А пока — я здесь, если нужна ещё помощь с текущим бизнесом."
)

_CD_DECLINED_TEXT = "Понял, продолжаем 👍 Что ещё беспокоит?"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_playbook_text(section: str) -> str:
    pb = PLAYBOOKS[section]
    lines = [f"{pb['emoji']} <b>{pb['title']}</b>\n"]
    for i, (timeframe, action) in enumerate(pb["steps"], 1):
        lines.append(f"<b>Шаг {i}</b> ({timeframe})\n{action}\n")
    return "\n".join(lines)


def _build_business_context(user) -> str:
    parts = []
    if user.business_type:
        parts.append(f"тип бизнеса: {user.business_type}")
    if user.employee_count:
        parts.append(f"сотрудников: {user.employee_count}")
    if user.city:
        parts.append(f"город: {user.city}")
    return ", ".join(parts) if parts else ""


async def _check_signals_and_offer(
    message: Message,
    user_id: int,
    tg_user_id: int,
    text: str,
    state: FSMContext,
    section: str | None,
) -> None:
    """Детектирует сигналы; при ≥ 3 показывает оффер CrazyDrift."""
    signals = await detect_transition_signals(text)
    if not any(signals.values()):
        return

    async with AsyncSessionLocal() as db:
        repo = AKBotRepository(db)
        user = await repo.get_user(tg_user_id)
        if not user or user.cd_lead_sent:
            return
        await repo.add_signals(user_id, signals, text)
        total = await repo.count_signals(user_id)
        await db.commit()

    # section change_direction всегда триггерит оффер
    force_offer = section == "change_direction"

    if total >= 3 or force_offer:
        await asyncio.sleep(0.8)
        await message.answer(_CD_OFFER_TEXT, parse_mode="HTML", reply_markup=cd_offer_keyboard())


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    # Parse UTM из deep link: /start utm_source=yandex__utm_campaign=crisis
    payload = message.text.split(" ", 1)[1] if " " in message.text else ""
    utm_source = None
    if payload:
        for part in payload.split("__"):
            if part.startswith("utm_source="):
                utm_source = part.split("=", 1)[1]

    async with AsyncSessionLocal() as db:
        repo = AKBotRepository(db)
        user, created = await repo.get_or_create_user(
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            utm_source=utm_source,
        )
        if not created:
            await repo.increment_session(user)
        await db.commit()

    await state.set_state(AKBotForm.main_menu)
    await state.update_data(section=None)

    name = message.from_user.first_name or ""
    greeting = name and f"Привет, {name}! 👋\n\n" or "Привет! 👋\n\n"
    text = (
        f"{greeting}"
        "Я антикризисный советник для малого бизнеса. "
        "Даю конкретные шаги — без воды и общих советов.\n\n"
        "Выберите вашу ситуацию:"
    )
    await message.answer(text, reply_markup=main_menu_keyboard())


# ── Выбор раздела ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("ak_sec_"))
async def cb_section(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    section = callback.data.removeprefix("ak_sec_")
    if section not in PLAYBOOKS:
        return

    async with AsyncSessionLocal() as db:
        repo = AKBotRepository(db)
        user = await repo.get_user(callback.from_user.id)
        if user:
            await repo.log_message(user.id, "user", f"[открыл раздел: {section}]", section)
            await db.commit()

    await state.set_state(AKBotForm.playbook_shown)
    await state.update_data(section=section)

    text = _build_playbook_text(section)
    await callback.message.answer(text, parse_mode="HTML", reply_markup=playbook_keyboard(section))

    # Раздел "смена направления" — сразу запускаем проверку сигналов
    if section == "change_direction":
        async with AsyncSessionLocal() as db:
            repo = AKBotRepository(db)
            user = await repo.get_user(callback.from_user.id)
            if user and not user.cd_lead_sent:
                await repo.add_signals(
                    user.id,
                    {"wants_alternative": True, "tired_business": False,
                     "has_capital": False, "asked_franchise": False},
                    "[открыл раздел: смена направления]",
                )
                total = await repo.count_signals(user.id)
                await db.commit()

            if user and not user.cd_lead_sent and total >= 1:
                await asyncio.sleep(1.2)
                await callback.message.answer(
                    _CD_OFFER_TEXT, parse_mode="HTML", reply_markup=cd_offer_keyboard()
                )


# ── Кнопка «Уточнить под мой бизнес» ─────────────────────────────────────────

@router.callback_query(F.data.startswith("ak_deepen_"))
async def cb_deepen(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    section = callback.data.removeprefix("ak_deepen_")

    # Смотрим, есть ли уже бизнес-контекст
    async with AsyncSessionLocal() as db:
        repo = AKBotRepository(db)
        user = await repo.get_user(callback.from_user.id)
        has_context = bool(user and user.business_type)

    await state.update_data(section=section)

    if has_context:
        await state.set_state(AKBotForm.ai_chat)
        await callback.message.answer(
            "Расскажите подробнее о вашей ситуации — что именно происходит? "
            "Постараюсь дать конкретный совет.",
            reply_markup=back_menu_keyboard(),
        )
    else:
        await state.set_state(AKBotForm.awaiting_context)
        await callback.message.answer(
            "Чтобы совет был точнее — пара быстрых вопросов.\n\n"
            "Какой у вас бизнес? (например: кафе, магазин одежды, услуги ремонта)",
            reply_markup=back_menu_keyboard(),
        )


# ── Сбор контекста (тип бизнеса) ─────────────────────────────────────────────

@router.message(AKBotForm.awaiting_context)
async def process_context(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    step = data.get("context_step", "business_type")

    if step == "business_type":
        async with AsyncSessionLocal() as db:
            repo = AKBotRepository(db)
            user = await repo.get_user(message.from_user.id)
            if user:
                await repo.update_user(user, business_type=message.text.strip()[:100])
                await db.commit()

        await state.update_data(context_step="employees")
        await message.answer(
            "Понял. Сколько у вас сотрудников? (можно примерно: 1, 3–5, 10+)",
            reply_markup=back_menu_keyboard(),
        )
    elif step == "employees":
        async with AsyncSessionLocal() as db:
            repo = AKBotRepository(db)
            user = await repo.get_user(message.from_user.id)
            if user:
                await repo.update_user(user, employee_count=message.text.strip()[:50])
                await db.commit()

        await state.set_state(AKBotForm.ai_chat)
        await state.update_data(context_step=None)
        await message.answer(
            "Отлично. Теперь расскажите подробнее о вашей ситуации — что конкретно происходит?",
            reply_markup=back_menu_keyboard(),
        )


# ── Свободный AI-чат ──────────────────────────────────────────────────────────

@router.message(AKBotForm.ai_chat)
async def process_ai_chat(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    section = data.get("section", "start_from_zero")
    section_title = _SECTION_TITLES.get(section, "Антикризисные меры")

    # Показываем индикатор набора
    await message.bot.send_chat_action(message.chat.id, "typing")

    async with AsyncSessionLocal() as db:
        repo = AKBotRepository(db)
        user = await repo.get_user(message.from_user.id)
        if not user:
            await message.answer("Что-то пошло не так. Попробуйте /start")
            return
        business_context = _build_business_context(user)
        await repo.log_message(user.id, "user", message.text, section)
        user_id = user.id
        await db.commit()

    # Запрос к Claude
    reply = await get_antikrizis_advice(
        user_message=message.text,
        business_context=business_context,
        section_title=section_title,
    )

    async with AsyncSessionLocal() as db:
        repo = AKBotRepository(db)
        user = await repo.get_user(message.from_user.id)
        if user:
            await repo.log_message(user.id, "bot", reply, section)
            await db.commit()

    await message.answer(reply, reply_markup=back_menu_keyboard())

    # Асинхронная проверка сигналов
    asyncio.create_task(_check_signals_and_offer(
        message, user_id, message.from_user.id, message.text, state, section
    ))


# ── Назад к меню ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "ak_back_menu")
async def cb_back_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AKBotForm.main_menu)
    await state.update_data(section=None, context_step=None)
    await callback.message.answer("Выберите вашу ситуацию:", reply_markup=main_menu_keyboard())


# ── CrazyDrift оффер — Да ─────────────────────────────────────────────────────

@router.callback_query(F.data == "ak_cd_yes")
async def cb_cd_yes(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    async with AsyncSessionLocal() as db:
        repo = AKBotRepository(db)
        user = await repo.get_user(callback.from_user.id)
        if not user:
            return

        signals = user.signals
        last_messages = await repo.get_last_messages(user.id, limit=10)
        sections = await repo.get_sections_visited(user.id)

        await repo.update_user(user, cd_lead_sent=True)
        await db.commit()

        # Нотификация менеджеру
        await bot2_notifications.notify_ak_lead(user, signals, last_messages, sections)

    await callback.message.answer(_CD_CONFIRMED_TEXT, reply_markup=cd_contact_keyboard())


# ── CrazyDrift оффер — Нет ───────────────────────────────────────────────────

@router.callback_query(F.data == "ak_cd_no")
async def cb_cd_no(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AKBotForm.main_menu)
    await callback.message.answer(_CD_DECLINED_TEXT, reply_markup=main_menu_keyboard())


# ── Сообщения вне состояния (fallback) ───────────────────────────────────────

@router.message(AKBotForm.main_menu)
@router.message(AKBotForm.playbook_shown)
async def fallback_menu(message: Message, state: FSMContext) -> None:
    """Если пользователь пишет текст вместо нажатия кнопки — переводим в AI-чат."""
    await state.set_state(AKBotForm.ai_chat)
    await process_ai_chat(message, state)

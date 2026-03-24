from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)


def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Продолжить", callback_data="start_form")]
    ])


def need_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Хочу понять инвестиции", callback_data="need_investments")],
        [InlineKeyboardButton(text="📈 Интересует доходность", callback_data="need_revenue")],
        [InlineKeyboardButton(text="📋 Нужны условия франшизы", callback_data="need_conditions")],
        [InlineKeyboardButton(text="🚀 Интересует запуск", callback_data="need_launch")],
        [InlineKeyboardButton(text="📊 Хочу финансовую модель", callback_data="need_financial")],
        [InlineKeyboardButton(text="💬 Другое", callback_data="need_other")],
    ])


def phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def materials_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏢 О нас", callback_data="mat_about")],
        [InlineKeyboardButton(text="📄 Презентация", callback_data="mat_presentation")],
        [InlineKeyboardButton(text="📊 Финансовая модель", callback_data="mat_finance")],
        [InlineKeyboardButton(text="🌐 Сайт", callback_data="mat_site")],
        [InlineKeyboardButton(text="▶️ YouTube", callback_data="mat_youtube")],
        [InlineKeyboardButton(text="👤 Связь с менеджером", callback_data="mat_manager")],
    ])


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❓ FAQ", callback_data="menu_faq")],
        [InlineKeyboardButton(text="👤 Связь с менеджером", callback_data="menu_manager")],
        [InlineKeyboardButton(text="📅 Записаться на звонок", callback_data="menu_call")],
        [InlineKeyboardButton(text="📦 Получить материалы повторно", callback_data="menu_materials")],
    ])


def call_slots_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡️ В ближайшее время", callback_data="call_now")],
        [InlineKeyboardButton(text="🕘 09:00–13:00", callback_data="call_09")],
        [InlineKeyboardButton(text="🕐 13:00–17:00", callback_data="call_13")],
        [InlineKeyboardButton(text="🕔 17:00–21:00", callback_data="call_17")],
        [InlineKeyboardButton(text="⏳ Пока не готов", callback_data="call_later")],
    ])


def faq_categories_keyboard(categories: list) -> InlineKeyboardMarkup:
    buttons = []
    for cat in categories:
        buttons.append([InlineKeyboardButton(
            text=cat.name, callback_data=f"faq_cat_{cat.id}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def faq_items_keyboard(items: list, category_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for item in items:
        short = item.question[:40] + "..." if len(item.question) > 40 else item.question
        buttons.append([InlineKeyboardButton(
            text=short, callback_data=f"faq_item_{item.id}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 К категориям", callback_data="menu_faq")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def after_faq_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❓ Ещё вопросы", callback_data="menu_faq")],
        [InlineKeyboardButton(text="👤 Связь с менеджером", callback_data="menu_manager")],
        [InlineKeyboardButton(text="📅 Записаться на звонок", callback_data="menu_call")],
    ])

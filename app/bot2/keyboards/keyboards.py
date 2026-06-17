from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📉  Упала выручка",              callback_data="ak_sec_revenue_drop")],
        [InlineKeyboardButton(text="🏢  Проблемы с арендой",         callback_data="ak_sec_rent_problems")],
        [InlineKeyboardButton(text="👥  Персонал в кризис",          callback_data="ak_sec_personnel")],
        [InlineKeyboardButton(text="💳  Долги и кредиторы",          callback_data="ak_sec_debts")],
        [InlineKeyboardButton(text="📦  Поставщики подняли цены",    callback_data="ak_sec_suppliers")],
        [InlineKeyboardButton(text="🎯  Нет новых клиентов",         callback_data="ak_sec_no_clients")],
        [InlineKeyboardButton(text="💰  Нечем платить зарплату",     callback_data="ak_sec_no_salary")],
        [InlineKeyboardButton(text="🔄  Думаю сменить направление",  callback_data="ak_sec_change_direction")],
        [InlineKeyboardButton(text="🆘  Всё плохо — с чего начать", callback_data="ak_sec_start_from_zero")],
    ])


def playbook_keyboard(section: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🤖  Уточнить под мой бизнес",
            callback_data=f"ak_deepen_{section}",
        )],
        [InlineKeyboardButton(text="◀  Назад к меню", callback_data="ak_back_menu")],
    ])


def back_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀  Назад к меню", callback_data="ak_back_menu")],
    ])


def cd_offer_keyboard() -> InlineKeyboardMarkup:
    """CrazyDrift franchise offer."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅  Да, хочу узнать подробнее", callback_data="ak_cd_yes")],
        [InlineKeyboardButton(text="❌  Нет, продолжим",            callback_data="ak_cd_no")],
    ])


def cd_contact_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀  Вернуться в меню", callback_data="ak_back_menu")],
    ])

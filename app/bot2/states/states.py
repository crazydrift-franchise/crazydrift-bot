from aiogram.fsm.state import State, StatesGroup


class AKBotForm(StatesGroup):
    main_menu         = State()  # главное меню показано
    playbook_shown    = State()  # плейбук показан, ждём действия
    awaiting_context  = State()  # спросили про бизнес перед AI-углублением
    ai_chat           = State()  # свободный диалог с AI

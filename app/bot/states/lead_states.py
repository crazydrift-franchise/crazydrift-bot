from aiogram.fsm.state import State, StatesGroup


class LeadForm(StatesGroup):
    waiting_name = State()
    waiting_city = State()
    waiting_need = State()
    waiting_phone = State()
    main_menu = State()
    faq_category = State()
    faq_item = State()
    free_question = State()
    # Qualification block
    qual_goal = State()
    qual_experience = State()
    qual_budget = State()
    qual_stage = State()
    qual_funding = State()
    qual_timing = State()

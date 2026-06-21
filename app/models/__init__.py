from datetime import datetime
from sqlalchemy import (
    Integer, BigInteger, String, Text, Boolean, DateTime, Float,
    ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum


class LeadStatus(str, enum.Enum):
    new = "new"
    form_started = "form_started"
    materials_sent = "materials_sent"
    faq_engaged = "faq_engaged"
    call_requested = "call_requested"
    cold = "cold"
    warm = "warm"
    hot = "hot"


class LeadTemperature(str, enum.Enum):
    cold = "cold"
    warm = "warm"
    hot = "hot"


class EventType(str, enum.Enum):
    message = "message"
    click = "click"
    faq = "faq"
    faq_view = "faq_view"
    touch = "touch"
    gpt_reply = "gpt_reply"
    status_change = "status_change"
    drop_off = "drop_off"
    resume = "resume"
    manager_contact = "manager_contact"
    deal_update = "deal_update"


# ── Users ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    lead: Mapped["Lead"] = relationship("Lead", back_populates="user", uselist=False)


# ── Leads ────────────────────────────────────────────────────────────────────

class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    need: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[LeadStatus] = mapped_column(SAEnum(LeadStatus), default=LeadStatus.new)
    engagement_score: Mapped[int] = mapped_column(Integer, default=0)
    lead_temperature: Mapped[LeadTemperature] = mapped_column(
        SAEnum(LeadTemperature), default=LeadTemperature.cold
    )
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    call_slot: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # UTM
    utm_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_content: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Manager tools
    manager_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reminder_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    block_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Behavioral counters (auto-updated)
    messages_count: Mapped[int] = mapped_column(Integer, default=0)
    free_questions_count: Mapped[int] = mapped_column(Integer, default=0)
    faq_views_count: Mapped[int] = mapped_column(Integer, default=0)
    touches_received_count: Mapped[int] = mapped_column(Integer, default=0)
    session_count: Mapped[int] = mapped_column(Integer, default=0)
    # Material clicks
    presentation_clicked: Mapped[bool] = mapped_column(Boolean, default=False)
    finance_model_clicked: Mapped[bool] = mapped_column(Boolean, default=False)
    about_clicked: Mapped[bool] = mapped_column(Boolean, default=False)
    site_clicked: Mapped[bool] = mapped_column(Boolean, default=False)
    youtube_clicked: Mapped[bool] = mapped_column(Boolean, default=False)
    manager_clicked: Mapped[bool] = mapped_column(Boolean, default=False)
    # FAQ interest signals
    faq_categories_viewed: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    faq_questions_viewed: Mapped[str | None] = mapped_column(Text, nullable=True)   # JSON list
    # Geography extended
    region: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True, default="RU")
    population_bucket: Mapped[str | None] = mapped_column(String(50), nullable=True)  # до100k/100k-300k/300k-1m/1m+
    planned_opening_city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    has_location_already: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    urgency_level: Mapped[str | None] = mapped_column(String(50), nullable=True)  # now/3m/6m/year/exploring
    desired_opening_date: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Qualification
    current_decision_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # exploring/comparing/choosing/ready_call/ready_contract
    main_objection: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_contact_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # call/telegram/whatsapp/any
    contact_source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # phone/telegram_only/unknown

    # Financial qualification
    investment_budget_range: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # <3m/3-5m/5-10m/10m+/no_answer
    funding_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # own/credit/investor/partner/undecided
    has_initial_capital: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # yes/no/partial

    # Lead profile
    has_business_experience: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    business_experience_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    has_franchise_experience: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    wants_passive_model: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_owner_operator_intent: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Drop-off tracking
    drop_off_step: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # name/city/need/phone/materials/faq
    drop_off_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Manager CRM
    manager_assigned: Mapped[str | None] = mapped_column(String(255), nullable=True)
    manager_first_contact_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    manager_contact_attempts: Mapped[int] = mapped_column(Integer, default=0)
    call_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    deal_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # none/contacted/qualified/negotiating/won/lost
    deal_won: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    loss_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Interest signals from messages (auto-detected)
    interest_investments: Mapped[bool] = mapped_column(Boolean, default=False)
    interest_revenue: Mapped[bool] = mapped_column(Boolean, default=False)
    interest_launch: Mapped[bool] = mapped_column(Boolean, default=False)
    interest_support: Mapped[bool] = mapped_column(Boolean, default=False)
    interest_territory: Mapped[bool] = mapped_column(Boolean, default=False)
    interest_risks: Mapped[bool] = mapped_column(Boolean, default=False)
    interest_payback: Mapped[bool] = mapped_column(Boolean, default=False)
    interest_royalty: Mapped[bool] = mapped_column(Boolean, default=False)
    interest_construction: Mapped[bool] = mapped_column(Boolean, default=False)
    interest_real_cases: Mapped[bool] = mapped_column(Boolean, default=False)
    interest_financing: Mapped[bool] = mapped_column(Boolean, default=False)
    interest_credit: Mapped[bool] = mapped_column(Boolean, default=False)
    interest_exclusivity: Mapped[bool] = mapped_column(Boolean, default=False)

    # FAQ interest scores (0-100)
    faq_financial_score: Mapped[int] = mapped_column(Integer, default=0)
    faq_legal_score: Mapped[int] = mapped_column(Integer, default=0)
    faq_launch_score: Mapped[int] = mapped_column(Integer, default=0)
    faq_risk_score: Mapped[int] = mapped_column(Integer, default=0)

    # Extended UTM
    utm_term: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ad_platform: Mapped[str | None] = mapped_column(String(100), nullable=True)
    first_touch_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # AI analysis scores
    intent_score: Mapped[int] = mapped_column(Integer, default=0)
    commercial_readiness_score: Mapped[int] = mapped_column(Integer, default=0)
    ai_priority: Mapped[str | None] = mapped_column(String(20), nullable=True)  # high/medium/low
    ai_contact_recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_script_recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped[User] = relationship("User", back_populates="lead")
    events: Mapped[list["LeadEvent"]] = relationship("LeadEvent", back_populates="lead")


# ── Lead Events ──────────────────────────────────────────────────────────────

class LeadEvent(Base):
    __tablename__ = "lead_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("leads.id"), index=True)
    event_type: Mapped[EventType] = mapped_column(SAEnum(EventType))
    event_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    lead: Mapped[Lead] = relationship("Lead", back_populates="events")


# ── FAQ ──────────────────────────────────────────────────────────────────────

class FaqCategory(Base):
    __tablename__ = "faq_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    items: Mapped[list["FaqItem"]] = relationship("FaqItem", back_populates="category")


class FaqItem(Base):
    __tablename__ = "faq_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("faq_categories.id"))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Follow-up рассылка
    followup_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    followup_delay_hours: Mapped[int] = mapped_column(Integer, default=24)  # через сколько часов
    followup_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    followup_buttons: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list

    category: Mapped[FaqCategory] = relationship("FaqCategory", back_populates="items")


# ── Knowledge Base ───────────────────────────────────────────────────────────

class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[str] = mapped_column(String(500), default="")  # comma-separated
    category: Mapped[str] = mapped_column(String(255), default="Общее")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


# ── Touches ──────────────────────────────────────────────────────────────────

class Touch(Base):
    __tablename__ = "touches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    send_mode: Mapped[str] = mapped_column(String(50), default="static")
    reply_mode: Mapped[str] = mapped_column(String(50), default="none")
    schedule: Mapped[str] = mapped_column(String(255), default="")
    segment: Mapped[str] = mapped_column(String(100), default="all")
    message_text: Mapped[str] = mapped_column(Text, default="")
    gpt_prompt: Mapped[str] = mapped_column(Text, default="")
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── GPT Settings ─────────────────────────────────────────────────────────────

class GptSettings(Base):
    __tablename__ = "gpt_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    analysis_prompt: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(100), default="claude-sonnet-4-20250514")
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, default=1000)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


# ── Touch Send Log (защита от дублей) ───────────────────────────────────────

class TouchSendLog(Base):
    __tablename__ = "touch_send_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    touch_id: Mapped[int] = mapped_column(Integer, ForeignKey("touches.id"), index=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("leads.id"), index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── Lead Notes ───────────────────────────────────────────────────────────────

class LeadNote(Base):
    __tablename__ = "lead_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("leads.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    remind_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    remind_3h_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    remind_1h_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    remind_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column(String(100), default="admin")


# ── Tasks ────────────────────────────────────────────────────────────────────

class TaskStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"


class TaskPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    lead_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("leads.id"), nullable=True, index=True)
    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), default=TaskStatus.todo)
    priority: Mapped[TaskPriority] = mapped_column(SAEnum(TaskPriority), default=TaskPriority.medium)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Knowledge Categories ──────────────────────────────────────────────────────

class KnowledgeCategory(Base):
    __tablename__ = "knowledge_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── Lead Status History ───────────────────────────────────────────────────────

class LeadStatusHistory(Base):
    __tablename__ = "lead_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("leads.id"), index=True)
    old_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    new_status: Mapped[str] = mapped_column(String(50))
    changed_by: Mapped[str] = mapped_column(String(50), default="system")  # "bot" / "admin"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── Broadcasts ────────────────────────────────────────────────────────────────

class BroadcastStatus(str, enum.Enum):
    scheduled = "scheduled"
    sent = "sent"
    failed = "failed"
    cancelled = "cancelled"


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[BroadcastStatus] = mapped_column(
        SAEnum(BroadcastStatus, name="broadcast_status"), default=BroadcastStatus.scheduled
    )
    filters: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── Bot Flow ──────────────────────────────────────────────────────────────────

class BotFlow(Base):
    __tablename__ = "bot_flows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), default="main")
    flow_json: Mapped[str] = mapped_column(Text)  # JSON nodes+edges
    is_active: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── AI Analysis History ───────────────────────────────────────────────────────

class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date_from: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_to: Mapped[str | None] = mapped_column(String(20), nullable=True)
    leads_count: Mapped[int] = mapped_column(Integer, default=0)
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── FAQ Follow-up Log ─────────────────────────────────────────────────────────

class FaqFollowupLog(Base):
    __tablename__ = "faq_followup_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("leads.id"))
    faq_item_id: Mapped[int] = mapped_column(Integer, ForeignKey("faq_items.id"))
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── Conversation Logs ─────────────────────────────────────────────────────────

class MessageRole(str, enum.Enum):
    user = "user"
    bot = "bot"
    gpt = "gpt"


class ConversationLog(Base):
    __tablename__ = "conversation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("leads.id"), index=True)
    role: Mapped[MessageRole] = mapped_column(SAEnum(MessageRole, name="message_role"))
    text: Mapped[str] = mapped_column(Text)
    # Derived signals (filled by NLP on save)
    detected_intent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # budget_question/roi/territory/support/risk/comparison/ready_to_call/other
    sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # positive/neutral/negative/curious
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── Lead Archive ──────────────────────────────────────────────────────────────

class LeadArchive(Base):
    """Snapshot of lead data + related records before chat reset."""
    __tablename__ = "lead_archives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("leads.id"), index=True)
    archived_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reason: Mapped[str] = mapped_column(String(255), default="chat_reset")
    lead_snapshot: Mapped[str] = mapped_column(Text)   # JSON snapshot of lead
    events_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)   # JSON list
    notes_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)    # JSON list
    tasks_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)    # JSON list
    broadcasts_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    status_history_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)


# ── Knowledge Recommendations ─────────────────────────────────────────────────

class KnowledgeRecommendation(Base):
    __tablename__ = "knowledge_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), default="ai_analysis")
    recommendation_type: Mapped[str] = mapped_column(String(50), default="faq")  # faq / knowledge_base
    # Lead info
    lead_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("leads.id"), nullable=True)
    lead_event_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("lead_events.id"), nullable=True)
    # Message content
    lead_message: Mapped[str | None] = mapped_column(Text, nullable=True)   # Сообщение лида
    ai_response: Mapped[str | None] = mapped_column(Text, nullable=True)    # Ответ AI боту
    message_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lead_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # AI generated content
    question: Mapped[str] = mapped_column(Text)
    answer_variant_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_variant_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_variant_3: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    is_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

from app.models.bot2_models import AKUser, AKSignal, AKMessage  # noqa

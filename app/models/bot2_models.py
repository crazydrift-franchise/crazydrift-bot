from datetime import datetime
from sqlalchemy import Integer, BigInteger, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class AKUser(Base):
    """Пользователь антикризисного советника."""
    __tablename__ = "ak_users"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None]  = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Профиль бизнеса (собирается по ходу диалога)
    business_type: Mapped[str | None]  = mapped_column(String(255), nullable=True)
    employee_count: Mapped[str | None] = mapped_column(String(50),  nullable=True)
    city: Mapped[str | None]           = mapped_column(String(255), nullable=True)

    # Трекинг
    utm_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    session_count: Mapped[int]     = mapped_column(Integer, default=1)
    last_active_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime]     = mapped_column(DateTime, default=datetime.utcnow)

    # Флаг: был ли передан как лид в CrazyDrift
    cd_lead_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    signals: Mapped[list["AKSignal"]] = relationship("AKSignal", back_populates="user")
    messages: Mapped[list["AKMessage"]] = relationship("AKMessage", back_populates="user")


class AKSignal(Base):
    """Сигнал перехода к франшизе CrazyDrift."""
    __tablename__ = "ak_signals"

    id: Mapped[int]        = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int]   = mapped_column(Integer, ForeignKey("ak_users.id"), index=True)
    signal_type: Mapped[str] = mapped_column(String(50))   # tired_business | has_capital | wants_alternative | asked_franchise
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["AKUser"] = relationship("AKUser", back_populates="signals")


class AKMessage(Base):
    """Лог сообщений для формирования лид-карточки."""
    __tablename__ = "ak_messages"

    id: Mapped[int]        = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int]   = mapped_column(Integer, ForeignKey("ak_users.id"), index=True)
    role: Mapped[str]      = mapped_column(String(10))   # user | bot
    text: Mapped[str]      = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["AKUser"] = relationship("AKUser", back_populates="messages")

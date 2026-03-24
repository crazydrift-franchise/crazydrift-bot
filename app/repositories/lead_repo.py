from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
from app.models import User, Lead, LeadEvent, LeadStatus, LeadTemperature, EventType


class LeadRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Users ────────────────────────────────────────────────────────────────

    async def get_or_create_user(self, telegram_user_id: int, username: str | None,
                                  first_name: str | None, last_name: str | None) -> tuple[User, bool]:
        result = await self.db.execute(
            select(User).where(User.telegram_user_id == telegram_user_id)
        )
        user = result.scalar_one_or_none()
        created = False
        if not user:
            user = User(
                telegram_user_id=telegram_user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )
            self.db.add(user)
            await self.db.flush()
            created = True
        return user, created

    # ── Leads ─────────────────────────────────────────────────────────────────

    async def get_or_create_lead(self, user: User) -> tuple[Lead, bool]:
        result = await self.db.execute(
            select(Lead).where(Lead.user_id == user.id)
        )
        lead = result.scalar_one_or_none()
        created = False
        if not lead:
            lead = Lead(user_id=user.id)
            self.db.add(lead)
            await self.db.flush()
            created = True
        return lead, created

    async def get_lead_by_telegram_id(self, telegram_user_id: int) -> Lead | None:
        result = await self.db.execute(
            select(Lead)
            .join(User)
            .where(User.telegram_user_id == telegram_user_id)
            .options(selectinload(Lead.user))
        )
        return result.scalar_one_or_none()

    async def get_lead_by_id(self, lead_id: int) -> Lead | None:
        result = await self.db.execute(
            select(Lead).where(Lead.id == lead_id)
            .options(selectinload(Lead.user), selectinload(Lead.events))
        )
        return result.scalar_one_or_none()

    async def get_all_leads(self, skip: int = 0, limit: int = 100) -> list[Lead]:
        result = await self.db.execute(
            select(Lead)
            .options(selectinload(Lead.user))
            .order_by(Lead.created_at.desc())
            .offset(skip).limit(limit)
        )
        return result.scalars().all()

    async def get_leads_by_segment(self, segment: str) -> list[Lead]:
        query = select(Lead).options(selectinload(Lead.user))
        if segment == "no_phone":
            query = query.where(Lead.phone.is_(None))
        elif segment == "materials_sent":
            query = query.where(Lead.status == LeadStatus.materials_sent)
        elif segment == "hot":
            query = query.where(Lead.lead_temperature == LeadTemperature.hot)
        elif segment == "cold":
            query = query.where(Lead.lead_temperature == LeadTemperature.cold)
        elif segment == "warm":
            query = query.where(Lead.lead_temperature == LeadTemperature.warm)
        elif segment == "call_requested":
            query = query.where(Lead.status == LeadStatus.call_requested)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def update_lead(self, lead: Lead, **kwargs) -> Lead:
        for key, value in kwargs.items():
            setattr(lead, key, value)
        lead.updated_at = datetime.utcnow()
        await self.db.flush()
        return lead

    # ── Stats ─────────────────────────────────────────────────────────────────

    async def get_stats(self) -> dict:
        total = await self.db.scalar(select(func.count(Lead.id)))
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0)
        today = await self.db.scalar(
            select(func.count(Lead.id)).where(Lead.created_at >= today_start)
        )
        week_start = datetime.utcnow() - timedelta(days=7)
        week = await self.db.scalar(
            select(func.count(Lead.id)).where(Lead.created_at >= week_start)
        )
        hot = await self.db.scalar(
            select(func.count(Lead.id)).where(Lead.lead_temperature == LeadTemperature.hot)
        )
        warm = await self.db.scalar(
            select(func.count(Lead.id)).where(Lead.lead_temperature == LeadTemperature.warm)
        )
        cold = await self.db.scalar(
            select(func.count(Lead.id)).where(Lead.lead_temperature == LeadTemperature.cold)
        )
        with_phone = await self.db.scalar(
            select(func.count(Lead.id)).where(Lead.phone.isnot(None))
        )
        return {
            "total": total or 0,
            "today": today or 0,
            "week": week or 0,
            "hot": hot or 0,
            "warm": warm or 0,
            "cold": cold or 0,
            "with_phone": with_phone or 0,
        }

    # ── Events ────────────────────────────────────────────────────────────────

    async def add_event(self, lead_id: int, event_type: EventType, event_data: str) -> LeadEvent:
        event = LeadEvent(lead_id=lead_id, event_type=event_type, event_data=event_data)
        self.db.add(event)
        await self.db.flush()
        return event

    async def get_lead_events(self, lead_id: int) -> list[LeadEvent]:
        result = await self.db.execute(
            select(LeadEvent)
            .where(LeadEvent.lead_id == lead_id)
            .order_by(LeadEvent.created_at.desc())
        )
        return result.scalars().all()

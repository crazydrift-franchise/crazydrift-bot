from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.bot2_models import AKUser, AKSignal, AKMessage


class AKBotRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Users ─────────────────────────────────────────────────────────────────

    async def get_or_create_user(
        self,
        telegram_user_id: int,
        username: str | None,
        first_name: str | None,
        utm_source: str | None = None,
    ) -> tuple[AKUser, bool]:
        result = await self.db.execute(
            select(AKUser).where(AKUser.telegram_user_id == telegram_user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            return user, False
        user = AKUser(
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
            utm_source=utm_source,
        )
        self.db.add(user)
        await self.db.flush()
        return user, True

    async def get_user(self, telegram_user_id: int) -> AKUser | None:
        result = await self.db.execute(
            select(AKUser).where(AKUser.telegram_user_id == telegram_user_id)
        )
        return result.scalar_one_or_none()

    async def update_user(self, user: AKUser, **kwargs) -> AKUser:
        for k, v in kwargs.items():
            setattr(user, k, v)
        user.last_active_at = datetime.utcnow()
        await self.db.flush()
        return user

    async def increment_session(self, user: AKUser) -> None:
        user.session_count += 1
        user.last_active_at = datetime.utcnow()
        await self.db.flush()

    # ── Signals ───────────────────────────────────────────────────────────────

    async def add_signals(self, user_id: int, signals: dict, source_text: str) -> None:
        """signals = {tired_business: bool, has_capital: bool, ...}"""
        for signal_type, triggered in signals.items():
            if not triggered:
                continue
            # Дедупликация: один тип сигнала — один раз
            exists = await self.db.execute(
                select(AKSignal.id).where(
                    AKSignal.user_id == user_id,
                    AKSignal.signal_type == signal_type,
                )
            )
            if exists.scalar_one_or_none():
                continue
            self.db.add(AKSignal(
                user_id=user_id,
                signal_type=signal_type,
                source_text=source_text[:500],
            ))
        await self.db.flush()

    async def count_signals(self, user_id: int) -> int:
        result = await self.db.execute(
            select(func.count()).where(AKSignal.user_id == user_id)
        )
        return result.scalar_one() or 0

    async def get_signal_types(self, user_id: int) -> list[str]:
        result = await self.db.execute(
            select(AKSignal.signal_type).where(AKSignal.user_id == user_id)
        )
        return [row[0] for row in result.fetchall()]

    # ── Messages ──────────────────────────────────────────────────────────────

    async def log_message(
        self, user_id: int, role: str, text: str, section: str | None = None
    ) -> None:
        self.db.add(AKMessage(
            user_id=user_id,
            role=role,
            text=text[:2000],
            section=section,
        ))
        await self.db.flush()

    async def get_last_messages(self, user_id: int, limit: int = 10) -> list[AKMessage]:
        result = await self.db.execute(
            select(AKMessage)
            .where(AKMessage.user_id == user_id)
            .order_by(AKMessage.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def get_sections_visited(self, user_id: int) -> list[str]:
        result = await self.db.execute(
            select(AKMessage.section)
            .where(AKMessage.user_id == user_id, AKMessage.section.isnot(None))
            .distinct()
        )
        return [row[0] for row in result.fetchall()]

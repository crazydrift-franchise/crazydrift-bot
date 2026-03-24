from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models import FaqCategory, FaqItem, KnowledgeItem, Touch, GptSettings


class FaqRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_categories(self) -> list[FaqCategory]:
        result = await self.db.execute(
            select(FaqCategory)
            .where(FaqCategory.is_active == True)
            .order_by(FaqCategory.order)
            .options(selectinload(FaqCategory.items))
        )
        return result.scalars().all()

    async def get_all_categories(self) -> list[FaqCategory]:
        result = await self.db.execute(
            select(FaqCategory).order_by(FaqCategory.order)
            .options(selectinload(FaqCategory.items))
        )
        return result.scalars().all()

    async def get_active_items_by_category(self, category_id: int) -> list[FaqItem]:
        result = await self.db.execute(
            select(FaqItem)
            .where(FaqItem.category_id == category_id, FaqItem.is_active == True)
            .order_by(FaqItem.order)
        )
        return result.scalars().all()

    async def get_item_by_id(self, item_id: int) -> FaqItem | None:
        result = await self.db.execute(
            select(FaqItem).where(FaqItem.id == item_id)
        )
        return result.scalar_one_or_none()

    async def create_category(self, name: str, order: int = 0) -> FaqCategory:
        cat = FaqCategory(name=name, order=order)
        self.db.add(cat)
        await self.db.flush()
        return cat

    async def create_item(self, category_id: int, question: str, answer: str, order: int = 0) -> FaqItem:
        item = FaqItem(category_id=category_id, question=question, answer=answer, order=order)
        self.db.add(item)
        await self.db.flush()
        return item


class KnowledgeRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all(self) -> list[KnowledgeItem]:
        result = await self.db.execute(
            select(KnowledgeItem).order_by(KnowledgeItem.updated_at.desc())
        )
        return result.scalars().all()

    async def get_as_text(self) -> str:
        """Returns all knowledge as formatted text for AI context."""
        items = await self.get_all()
        if not items:
            return "База знаний пуста."
        parts = []
        for item in items:
            parts.append(f"## {item.title}\n{item.content}")
        return "\n\n".join(parts)


class TouchRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_touches(self) -> list[Touch]:
        result = await self.db.execute(
            select(Touch).where(Touch.is_active == True)
        )
        return result.scalars().all()

    async def get_all(self) -> list[Touch]:
        result = await self.db.execute(select(Touch).order_by(Touch.created_at))
        return result.scalars().all()

    async def increment_sent(self, touch_id: int):
        touch = await self.db.get(Touch, touch_id)
        if touch:
            touch.sent_count += 1
            await self.db.flush()


class GptSettingsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self) -> GptSettings | None:
        result = await self.db.execute(select(GptSettings).limit(1))
        return result.scalar_one_or_none()

    async def get_or_create(self) -> GptSettings:
        settings = await self.get()
        if not settings:
            settings = GptSettings(
                system_prompt=(
                    "Ты — виртуальный помощник по франшизе CrazyDrift. "
                    "Отвечай только на основе базы знаний. "
                    "Не придумывай цифры, не обещай прибыль, не давай юридические гарантии. "
                    "Будь вежлив, профессионален, кратко и по делу."
                ),
                analysis_prompt=(
                    "Проанализируй активность лида и верни JSON: "
                    "{engagement_score: 0-100, lead_temperature: cold|warm|hot, "
                    "summary: string, recommended_action: string}"
                ),
            )
            self.db.add(settings)
            await self.db.flush()
        return settings

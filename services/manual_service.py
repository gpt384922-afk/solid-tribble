from __future__ import annotations

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload

from db.models import Manual, ManualCategory, ManualTag
from services.schemas import ManualCreateSchema


class ManualService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_manual(self, payload: ManualCreateSchema) -> Manual:
        manual = Manual(
            owner_telegram_id=payload.owner_telegram_id,
            title=payload.title,
            category=payload.category,
            body_markdown=payload.body_markdown,
            tags=[ManualTag(tag=t) for t in payload.tags],
        )
        async with self._session_factory() as session:
            session.add(manual)
            await session.commit()
            await session.refresh(manual)
            return manual

    async def list_categories(self, owner_telegram_id: int) -> list[tuple[ManualCategory, int]]:
        async with self._session_factory() as session:
            rows = await session.execute(
                select(Manual.category, Manual.id)
                .where(Manual.owner_telegram_id == owner_telegram_id)
                .order_by(Manual.category)
            )
            stats: dict[ManualCategory, int] = {}
            for category, _ in rows.all():
                stats[category] = stats.get(category, 0) + 1
            return sorted(stats.items(), key=lambda x: x[0].value)

    async def list_manuals(self, owner_telegram_id: int, category: ManualCategory | None = None) -> list[Manual]:
        query = select(Manual).where(Manual.owner_telegram_id == owner_telegram_id).options(joinedload(Manual.tags)).order_by(Manual.updated_at.desc())
        if category:
            query = query.where(Manual.category == category)
        async with self._session_factory() as session:
            rows = await session.scalars(query)
            return list(rows.unique().all())

    async def search_manuals(self, owner_telegram_id: int, text: str) -> list[Manual]:
        like = f"%{text}%"
        query = (
            select(Manual)
            .outerjoin(ManualTag, ManualTag.manual_id == Manual.id)
            .where(
                Manual.owner_telegram_id == owner_telegram_id,
                or_(
                    Manual.title.ilike(like),
                    Manual.body_markdown.ilike(like),
                    ManualTag.tag.ilike(like),
                ),
            )
            .options(joinedload(Manual.tags))
            .order_by(Manual.updated_at.desc())
        )

        async with self._session_factory() as session:
            rows = await session.scalars(query)
            return list(rows.unique().all())

    async def get_manual(self, owner_telegram_id: int, manual_id: int) -> Manual | None:
        async with self._session_factory() as session:
            return await session.scalar(
                select(Manual).where(Manual.id == manual_id, Manual.owner_telegram_id == owner_telegram_id).options(joinedload(Manual.tags))
            )

    async def update_manual(
        self,
        owner_telegram_id: int,
        manual_id: int,
        title: str,
        category: ManualCategory,
        tags: list[str],
        body_markdown: str,
    ) -> bool:
        async with self._session_factory() as session:
            manual = await session.scalar(
                select(Manual).where(Manual.id == manual_id, Manual.owner_telegram_id == owner_telegram_id).options(joinedload(Manual.tags))
            )
            if manual is None:
                return False
            manual.title = title
            manual.category = category
            manual.body_markdown = body_markdown
            manual.tags.clear()
            manual.tags.extend(ManualTag(tag=t) for t in tags)
            await session.commit()
            return True

    async def delete_manual(self, owner_telegram_id: int, manual_id: int) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(delete(Manual).where(Manual.id == manual_id, Manual.owner_telegram_id == owner_telegram_id))
            await session.commit()
            return result.rowcount > 0

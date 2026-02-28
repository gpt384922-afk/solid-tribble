from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models import AccessUser


class AccessService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def bootstrap_admin(self, admin_telegram_id: int) -> None:
        async with self._session_factory() as session:
            user = await session.scalar(select(AccessUser).where(AccessUser.telegram_id == admin_telegram_id))
            if user is None:
                session.add(AccessUser(telegram_id=admin_telegram_id, is_admin=True))
                await session.commit()
                return
            if not user.is_admin:
                user.is_admin = True
                await session.commit()

    async def is_allowed(self, telegram_id: int) -> bool:
        async with self._session_factory() as session:
            row = await session.scalar(select(AccessUser.id).where(AccessUser.telegram_id == telegram_id))
            return row is not None

    async def is_admin(self, telegram_id: int) -> bool:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(AccessUser.id).where(AccessUser.telegram_id == telegram_id, AccessUser.is_admin.is_(True))
            )
            return row is not None

    async def add_to_whitelist(self, telegram_id: int, is_admin: bool = False) -> None:
        async with self._session_factory() as session:
            existing = await session.scalar(select(AccessUser).where(AccessUser.telegram_id == telegram_id))
            if existing is None:
                session.add(AccessUser(telegram_id=telegram_id, is_admin=is_admin))
            else:
                existing.is_admin = existing.is_admin or is_admin
            await session.commit()

    async def remove_from_whitelist(self, telegram_id: int) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(delete(AccessUser).where(AccessUser.telegram_id == telegram_id))
            await session.commit()
            return result.rowcount > 0

    async def list_whitelist(self) -> list[AccessUser]:
        async with self._session_factory() as session:
            result = await session.scalars(select(AccessUser).order_by(AccessUser.is_admin.desc(), AccessUser.telegram_id))
            return list(result)

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models import AppSetting


class SettingsService:
    SECRET_TTL_KEY = "secret_ttl_seconds"

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], default_secret_ttl: int) -> None:
        self._session_factory = session_factory
        self._default_secret_ttl = default_secret_ttl

    async def get_secret_ttl(self) -> int:
        async with self._session_factory() as session:
            setting = await session.scalar(select(AppSetting).where(AppSetting.key == self.SECRET_TTL_KEY))
            if setting is None:
                return self._default_secret_ttl
            try:
                return int(setting.value)
            except ValueError:
                return self._default_secret_ttl

    async def set_secret_ttl(self, ttl_seconds: int) -> None:
        async with self._session_factory() as session:
            setting = await session.scalar(select(AppSetting).where(AppSetting.key == self.SECRET_TTL_KEY))
            if setting is None:
                session.add(AppSetting(key=self.SECRET_TTL_KEY, value=str(ttl_seconds)))
            else:
                setting.value = str(ttl_seconds)
            await session.commit()

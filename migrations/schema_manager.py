from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from db.base import Base
from db.models import SchemaVersion

logger = logging.getLogger(__name__)
CURRENT_SCHEMA_VERSION = 1


async def ensure_schema(engine: AsyncEngine, session_factory: async_sessionmaker) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        row = await session.scalar(select(SchemaVersion).limit(1))
        if row is None:
            session.add(SchemaVersion(version=CURRENT_SCHEMA_VERSION))
            await session.commit()
            logger.info("Инициализирована версия схемы: %s", CURRENT_SCHEMA_VERSION)
            return

        if row.version < CURRENT_SCHEMA_VERSION:
            await apply_manual_migrations(engine, row.version, CURRENT_SCHEMA_VERSION)
            row.version = CURRENT_SCHEMA_VERSION
            await session.commit()
            logger.info("Применены ручные миграции до версии: %s", CURRENT_SCHEMA_VERSION)


async def apply_manual_migrations(engine: AsyncEngine, from_version: int, to_version: int) -> None:
    logger.warning("Ручные миграции не требуются: from=%s to=%s", from_version, to_version)
    # Здесь можно добавлять последовательные ALTER TABLE, если схема будет расти.
    _ = engine

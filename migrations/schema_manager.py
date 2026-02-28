from __future__ import annotations

import logging

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from db.base import Base
from db.models import SchemaVersion

logger = logging.getLogger(__name__)
CURRENT_SCHEMA_VERSION = 2


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
    if from_version < 2 <= to_version:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE servers DROP COLUMN IF EXISTS status"))
            await conn.execute(text("DROP INDEX IF EXISTS ix_servers_owner_status"))
            await conn.execute(text("DROP TYPE IF EXISTS server_status_enum"))
            await conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_servers_owner_name ON servers (owner_telegram_id, name)")
            )
        logger.info("Миграция v2: удалено поле status и связанные объекты.")

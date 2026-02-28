from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from bot.config import get_settings
from bot.dependencies import build_services
from bot.handlers import billing_handlers, manual_handlers, menu_handlers, settings_handlers, vps_handlers
from bot.logging import setup_logging
from bot.middlewares.services import ServiceMiddleware
from bot.middlewares.whitelist import WhitelistMiddleware
from db.session import create_engine, create_session_factory
from migrations.schema_manager import ensure_schema

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    settings = get_settings()

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    await ensure_schema(engine, session_factory)

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    services = build_services(settings, bot, session_factory, engine)

    await services.access.bootstrap_admin(settings.admin_telegram_id)

    dp = Dispatcher()
    dp.update.middleware(ServiceMiddleware(services))
    dp.update.middleware(WhitelistMiddleware(services.access))

    dp.include_router(menu_handlers.router)
    dp.include_router(vps_handlers.router)
    dp.include_router(billing_handlers.router)
    dp.include_router(manual_handlers.router)
    dp.include_router(settings_handlers.router)

    services.reminders.start()

    logger.info("Бот запущен")
    try:
        await dp.start_polling(bot)
    finally:
        services.reminders.shutdown()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

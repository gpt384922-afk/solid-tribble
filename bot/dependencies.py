from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from bot.config import Settings
from crypto.secrets import SecretCipher
from services.access_service import AccessService
from services.billing_service import BillingService
from services.export_import_service import ExportImportService
from services.manual_service import ManualService
from services.reminder_service import ReminderService
from services.server_service import ServerService
from services.settings_service import SettingsService


@dataclass
class AppServices:
    access: AccessService
    settings: SettingsService
    servers: ServerService
    billing: BillingService
    manuals: ManualService
    export_import: ExportImportService
    reminders: ReminderService


def build_services(
    settings: Settings,
    bot: Bot,
    session_factory: async_sessionmaker,
    engine: AsyncEngine,
) -> AppServices:
    _ = engine
    cipher = SecretCipher(settings.bot_master_key)

    access = AccessService(session_factory)
    settings_service = SettingsService(session_factory, default_secret_ttl=settings.secret_ttl_seconds)
    server_service = ServerService(session_factory, cipher)
    billing_service = BillingService(session_factory)
    manual_service = ManualService(session_factory)
    export_import = ExportImportService(server_service, manual_service)
    reminders = ReminderService(bot, access, billing_service, settings.notify_hour_utc)

    return AppServices(
        access=access,
        settings=settings_service,
        servers=server_service,
        billing=billing_service,
        manuals=manual_service,
        export_import=export_import,
        reminders=reminders,
    )

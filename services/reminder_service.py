from __future__ import annotations

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from services.access_service import AccessService
from services.billing_service import BillingService

logger = logging.getLogger(__name__)


class ReminderService:
    def __init__(
        self,
        bot: Bot,
        access_service: AccessService,
        billing_service: BillingService,
        notify_hour_utc: int,
    ) -> None:
        self._bot = bot
        self._access_service = access_service
        self._billing_service = billing_service
        self._notify_hour_utc = notify_hour_utc
        self._scheduler = AsyncIOScheduler(timezone="UTC")

    def start(self) -> None:
        trigger = CronTrigger(hour=self._notify_hour_utc, minute=0)
        self._scheduler.add_job(self._run_reminders, trigger=trigger, id="expiry_reminders", replace_existing=True)
        self._scheduler.start()
        logger.info("Планировщик напоминаний запущен (UTC %s:00)", self._notify_hour_utc)

    async def _run_reminders(self) -> None:
        due = await self._billing_service.due_notifications([14, 7, 3, 1])
        if not due:
            logger.info("Напоминания: записей нет")
            return

        users = await self._access_service.list_whitelist()
        admins = [u.telegram_id for u in users if u.is_admin]
        if not admins:
            logger.warning("Нет админов для отправки уведомлений")
            return

        for server, billing, days_left in due:
            text = (
                "⏰ Напоминание об оплате\n"
                f"Сервер: {server.name}\n"
                f"IP: {server.ip4}\n"
                f"Истекает: {billing.expires_at.strftime('%d.%m.%Y')}\n"
                f"Осталось дней: {days_left}\n"
                f"Сумма: {billing.price_amount} {billing.price_currency}"
            )
            for admin_id in admins:
                try:
                    await self._bot.send_message(admin_id, text)
                except Exception:  # noqa: BLE001
                    logger.exception("Не удалось отправить уведомление admin_id=%s", admin_id)

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

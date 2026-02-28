from __future__ import annotations

import asyncio
from datetime import datetime

from aiogram import Bot
from aiogram.types import Message


def parse_date_ru(text: str) -> datetime.date:
    return datetime.strptime(text.strip(), "%d.%m.%Y").date()


async def send_temporary_secret(bot: Bot, chat_id: int, text: str, ttl_seconds: int) -> None:
    msg = await bot.send_message(chat_id, text)

    async def _delete_later(message: Message) -> None:
        await asyncio.sleep(ttl_seconds)
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        except Exception:  # noqa: BLE001
            return

    asyncio.create_task(_delete_later(msg))

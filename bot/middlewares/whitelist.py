from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from services.access_service import AccessService


class WhitelistMiddleware(BaseMiddleware):
    def __init__(self, access_service: AccessService) -> None:
        self._access_service = access_service

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = None
        event_user = data.get("event_from_user")
        if event_user and getattr(event_user, "id", None):
            user_id = int(event_user.id)
        elif isinstance(event, Message) and event.from_user:
            user_id = int(event.from_user.id)
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = int(event.from_user.id)

        if user_id is None:
            # Не передаем событие дальше без user_id, чтобы хендлеры не падали
            # на обязательном параметре user_id.
            return None

        allowed = await self._access_service.is_allowed(user_id)
        if not allowed:
            if isinstance(event, Message):
                await event.answer("Доступ запрещён.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Доступ запрещён.", show_alert=True)
            return None

        data["user_id"] = user_id
        data["is_admin"] = await self._access_service.is_admin(user_id)
        return await handler(event, data)

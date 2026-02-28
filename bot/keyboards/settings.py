from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def settings_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Показать whitelist", callback_data="settings:whitelist:list")],
            [InlineKeyboardButton(text="➕ Добавить в whitelist", callback_data="settings:whitelist:add")],
            [InlineKeyboardButton(text="➖ Удалить из whitelist", callback_data="settings:whitelist:remove")],
            [InlineKeyboardButton(text="🔐 TTL секрета", callback_data="settings:secret_ttl")],
            [InlineKeyboardButton(text="📤 Экспорт JSON", callback_data="settings:export")],
        ]
    )

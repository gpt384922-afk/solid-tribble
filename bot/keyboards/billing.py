from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def billing_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚠ В 7 дней", callback_data="bill:expiring:7")],
            [InlineKeyboardButton(text="📆 В 30 дней", callback_data="bill:expiring:30")],
            [InlineKeyboardButton(text="💰 Сводка за месяц", callback_data="bill:summary")],
            [InlineKeyboardButton(text="➕ Добавить оплату", callback_data="bill:add_start")],
        ]
    )


def billing_server_select_keyboard(items: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton(text=name, callback_data=f"bill:add:{server_id}")] for server_id, name in items]
    keyboard.append([InlineKeyboardButton(text="Отмена", callback_data="menu:billing")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

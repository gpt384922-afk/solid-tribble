from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def vps_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список серверов", callback_data="vps:list:1")],
            [InlineKeyboardButton(text="➕ Добавить сервер", callback_data="vps:add")],
            [InlineKeyboardButton(text="🔎 Поиск", callback_data="vps:search")],
            [InlineKeyboardButton(text="⏰ Истекают", callback_data="vps:expiring_menu")],
            [InlineKeyboardButton(text="⭐ Избранное", callback_data="vps:filter:favorites")],
        ]
    )


def expiring_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚠ В 7 дней", callback_data="vps:expiring:7")],
            [InlineKeyboardButton(text="📆 В 30 дней", callback_data="vps:expiring:30")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="menu:vps")],
        ]
    )


def server_list_keyboard(items: list[tuple[str, str]], page: int, total: int, page_size: int = 5) -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton(text=label, callback_data=f"vps:card:{server_id}")] for server_id, label in items]

    max_page = max(1, (total + page_size - 1) // page_size)
    if total > page_size:
        keyboard.append(
            [
                InlineKeyboardButton(text="⬅️", callback_data=f"vps:list:{max(1, page - 1)}"),
                InlineKeyboardButton(text=f"{page}/{max_page}", callback_data="noop"),
                InlineKeyboardButton(text="➡️", callback_data=f"vps:list:{min(max_page, page + 1)}"),
            ]
        )

    keyboard.append([InlineKeyboardButton(text="⬅ Назад", callback_data="menu:vps")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def server_card_keyboard(server_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"vps:delete_ask:{server_id}")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="vps:list:1")],
        ]
    )


def delete_confirm_keyboard(server_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, удалить", callback_data=f"vps:delete_confirm:{server_id}"),
                InlineKeyboardButton(text="Отмена", callback_data=f"vps:delete_cancel:{server_id}"),
            ]
        ]
    )


def add_server_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data="vps:add:confirm"),
                InlineKeyboardButton(text="❌ Отменить", callback_data="vps:add:cancel"),
            ]
        ]
    )

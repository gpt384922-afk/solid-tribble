from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def vps_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список серверов", callback_data="vps:list:1")],
            [InlineKeyboardButton(text="➕ Добавить сервер", callback_data="vps:add")],
            [InlineKeyboardButton(text="🔎 Поиск", callback_data="vps:search")],
            [
                InlineKeyboardButton(text="⏰ Истекают <=7 дней", callback_data="vps:filter:expiring_7"),
            ],
            [
                InlineKeyboardButton(text="✅ Активные", callback_data="vps:filter:active"),
                InlineKeyboardButton(text="🗄 Архив", callback_data="vps:filter:archived"),
            ],
            [InlineKeyboardButton(text="⭐ Избранное", callback_data="vps:filter:favorites")],
        ]
    )


def server_list_keyboard(items: list[tuple[str, str]], page: int, total: int, page_size: int = 5) -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton(text=name, callback_data=f"vps:card:{server_id}")] for server_id, name in items]

    max_page = max(1, (total + page_size - 1) // page_size)
    keyboard.append(
        [
            InlineKeyboardButton(text="⬅️", callback_data=f"vps:list:{max(1, page - 1)}"),
            InlineKeyboardButton(text=f"{page}/{max_page}", callback_data="noop"),
            InlineKeyboardButton(text="➡️", callback_data=f"vps:list:{min(max_page, page + 1)}"),
        ]
    )
    keyboard.append([InlineKeyboardButton(text="↩️ Назад", callback_data="menu:vps")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def server_card_keyboard(server_id: str, is_archived: bool, is_favorite: bool) -> InlineKeyboardMarkup:
    archive_text = "♻️ Восстановить" if is_archived else "🗄 Архивировать"
    favorite_text = "⭐ Убрать из избранного" if is_favorite else "⭐ В избранное"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Скопировать IP", callback_data=f"vps:copy_ip:{server_id}")],
            [InlineKeyboardButton(text="📋 Скопировать SSH", callback_data=f"vps:copy_ssh:{server_id}")],
            [InlineKeyboardButton(text="📋 Скопировать всё", callback_data=f"vps:copy_all:{server_id}")],
            [InlineKeyboardButton(text="🔒 Показать секрет", callback_data=f"vps:secret_ask:{server_id}")],
            [InlineKeyboardButton(text=favorite_text, callback_data=f"vps:favorite:{server_id}")],
            [InlineKeyboardButton(text=archive_text, callback_data=f"vps:archive:{server_id}")],
            [InlineKeyboardButton(text="➕ Добавить оплату", callback_data=f"bill:add:{server_id}")],
            [InlineKeyboardButton(text="↩️ К списку", callback_data="vps:list:1")],
        ]
    )


def secret_confirm_keyboard(server_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Показать", callback_data=f"vps:secret_show:{server_id}"),
                InlineKeyboardButton(text="Отмена", callback_data=f"vps:card:{server_id}"),
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

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

CATEGORY_TITLE = {
    "install": "Установка",
    "troubleshoot": "Диагностика",
    "upgrade": "Обновление",
    "other": "Другое",
}


def manuals_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📚 Категории", callback_data="manual:categories")],
            [InlineKeyboardButton(text="🔎 Поиск", callback_data="manual:search")],
            [InlineKeyboardButton(text="➕ Добавить статью", callback_data="manual:add")],
        ]
    )


def manual_categories_keyboard(items: list[tuple[str, int]]) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(
                text=f"{CATEGORY_TITLE.get(name, name)} ({count})",
                callback_data=f"manual:list:{name}",
            )
        ]
        for name, count in items
    ]
    keyboard.append([InlineKeyboardButton(text="↩️ Назад", callback_data="menu:manual")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def manual_list_keyboard(items: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton(text=title, callback_data=f"manual:view:{manual_id}")] for manual_id, title in items]
    keyboard.append([InlineKeyboardButton(text="↩️ Категории", callback_data="manual:categories")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def manual_card_keyboard(manual_id: int, is_admin: bool) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="📌 Только команды", callback_data=f"manual:commands:{manual_id}")],
    ]
    if is_admin:
        keyboard.append([InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"manual:edit:{manual_id}")])
        keyboard.append([InlineKeyboardButton(text="🗑 Удалить", callback_data=f"manual:delete:{manual_id}")])
    keyboard.append([InlineKeyboardButton(text="↩️ Назад", callback_data="manual:categories")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def manual_category_choose_keyboard() -> InlineKeyboardMarkup:
    items = [
        ("install", "Установка"),
        ("troubleshoot", "Диагностика"),
        ("upgrade", "Обновление"),
        ("other", "Другое"),
    ]
    keyboard = [[InlineKeyboardButton(text=title, callback_data=f"manual:cat_pick:{key}")] for key, title in items]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def add_manual_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data="manual:add:confirm"),
                InlineKeyboardButton(text="❌ Отменить", callback_data="manual:add:cancel"),
            ]
        ]
    )

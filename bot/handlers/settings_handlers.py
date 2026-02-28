from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.dependencies import AppServices
from bot.keyboards.main import CANCEL_MENU
from bot.keyboards.settings import settings_menu_keyboard
from bot.states.settings_states import SettingsStates, WhitelistStates

router = Router()


def _require_admin(is_admin: bool) -> bool:
    return is_admin


@router.callback_query(F.data == "settings:whitelist:list")
async def settings_whitelist_list(query: CallbackQuery, services: AppServices, is_admin: bool) -> None:
    if not _require_admin(is_admin):
        await query.answer("Только администратор", show_alert=True)
        return

    users = await services.access.list_whitelist()
    if not users:
        await query.message.answer("Whitelist пуст.")
        await query.answer()
        return

    lines = ["Whitelist:"]
    for user in users:
        role = "админ" if user.is_admin else "пользователь"
        lines.append(f"- {user.telegram_id} ({role})")
    await query.message.answer("\n".join(lines))
    await query.answer()


@router.callback_query(F.data == "settings:whitelist:add")
async def settings_whitelist_add_start(query: CallbackQuery, state: FSMContext, is_admin: bool) -> None:
    if not _require_admin(is_admin):
        await query.answer("Только администратор", show_alert=True)
        return

    await state.set_state(WhitelistStates.add_user)
    await query.message.answer("Введите Telegram user_id для добавления:", reply_markup=CANCEL_MENU)
    await query.answer()


@router.message(WhitelistStates.add_user)
async def settings_whitelist_add_apply(message: Message, state: FSMContext, services: AppServices) -> None:
    try:
        user_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("Нужно число (Telegram user_id).")
        return

    await services.access.add_to_whitelist(user_id)
    await state.clear()
    await message.answer(f"Пользователь {user_id} добавлен в whitelist.", reply_markup=settings_menu_keyboard())


@router.callback_query(F.data == "settings:whitelist:remove")
async def settings_whitelist_remove_start(query: CallbackQuery, state: FSMContext, is_admin: bool) -> None:
    if not _require_admin(is_admin):
        await query.answer("Только администратор", show_alert=True)
        return

    await state.set_state(WhitelistStates.remove_user)
    await query.message.answer("Введите Telegram user_id для удаления:", reply_markup=CANCEL_MENU)
    await query.answer()


@router.message(WhitelistStates.remove_user)
async def settings_whitelist_remove_apply(message: Message, state: FSMContext, services: AppServices) -> None:
    try:
        user_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("Нужно число (Telegram user_id).")
        return

    deleted = await services.access.remove_from_whitelist(user_id)
    await state.clear()
    await message.answer(
        f"Пользователь {user_id} удалён." if deleted else "Пользователь не найден.",
        reply_markup=settings_menu_keyboard(),
    )


@router.callback_query(F.data == "settings:secret_ttl")
async def settings_secret_ttl_show(query: CallbackQuery, state: FSMContext, services: AppServices, is_admin: bool) -> None:
    if not _require_admin(is_admin):
        await query.answer("Только администратор", show_alert=True)
        return

    ttl = await services.settings.get_secret_ttl()
    await state.set_state(SettingsStates.set_secret_ttl)
    await query.message.answer(
        f"Текущее время автоудаления секрета: {ttl} сек.\nВведите новое значение (10..300):",
        reply_markup=CANCEL_MENU,
    )
    await query.answer()


@router.message(SettingsStates.set_secret_ttl)
async def settings_secret_ttl_apply(message: Message, state: FSMContext, services: AppServices) -> None:
    try:
        ttl = int((message.text or "").strip())
        if ttl < 10 or ttl > 300:
            raise ValueError
    except ValueError:
        await message.answer("Время должно быть числом от 10 до 300 секунд.")
        return

    await services.settings.set_secret_ttl(ttl)
    await state.clear()
    await message.answer(f"Время автоудаления обновлено: {ttl} сек.", reply_markup=settings_menu_keyboard())


@router.callback_query(F.data == "settings:export")
async def settings_export(query: CallbackQuery, services: AppServices, user_id: int, is_admin: bool) -> None:
    if not _require_admin(is_admin):
        await query.answer("Только администратор", show_alert=True)
        return

    bundle = await services.export_import.export_user_data(user_id, include_secret=False)
    payload = bundle.to_json().encode("utf-8")
    file = BufferedInputFile(payload, filename="flow_proxy_export.json")
    await query.message.answer_document(file, caption="Экспорт готов (без секретов).")
    await query.answer()


@router.message(F.text.casefold() == "отмена")
async def settings_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current and current.startswith((WhitelistStates.__name__, SettingsStates.__name__)):
        await state.clear()
        await message.answer("Действие отменено.")

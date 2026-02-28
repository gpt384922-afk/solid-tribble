from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.dependencies import AppServices
from bot.keyboards.main import CANCEL_MENU
from bot.keyboards.manuals import (
    manual_card_keyboard,
    manual_categories_keyboard,
    manual_category_choose_keyboard,
    manual_list_keyboard,
)
from bot.states.manual_states import AddManualStates, EditManualStates, SearchManualState
from services.schemas import MANUAL_CATEGORY_MAP, ManualCreateSchema, parse_manual_commands, parse_tags_input

router = Router()

CATEGORY_TITLE = {
    "install": "Установка",
    "troubleshoot": "Диагностика",
    "upgrade": "Обновление",
    "other": "Другое",
}


def _format_manual_item(manual) -> str:
    tags = ", ".join(f"#{t.tag}" for t in manual.tags) if manual.tags else "-"
    return (
        f"<b>{manual.title}</b>\n"
        f"Категория: <code>{CATEGORY_TITLE.get(manual.category.value, manual.category.value)}</code>\n"
        f"Теги: {tags}\n\n"
        f"{manual.body_markdown}"
    )


@router.callback_query(F.data == "manual:categories")
async def manual_categories(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    items = await services.manuals.list_categories(user_id)
    if not items:
        await query.message.edit_text("Мануалов пока нет.")
        await query.answer()
        return

    payload = [(category.value, count) for category, count in items]
    await query.message.edit_text("Категории:", reply_markup=manual_categories_keyboard(payload))
    await query.answer()


@router.callback_query(F.data.startswith("manual:list:"))
async def manual_list(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    cat_key = query.data.split(":", maxsplit=2)[2]
    category = MANUAL_CATEGORY_MAP.get(cat_key)
    if category is None:
        await query.answer("Неизвестная категория", show_alert=True)
        return
    items = await services.manuals.list_manuals(user_id, category=category)
    if not items:
        await query.message.edit_text("В этой категории пусто.")
        await query.answer()
        return
    payload = [(m.id, m.title) for m in items]
    await query.message.edit_text(f"Категория: {CATEGORY_TITLE.get(cat_key, cat_key)}", reply_markup=manual_list_keyboard(payload))
    await query.answer()


@router.callback_query(F.data.startswith("manual:view:"))
async def manual_view(query: CallbackQuery, services: AppServices, user_id: int, is_admin: bool) -> None:
    manual_id = int(query.data.split(":", maxsplit=2)[2])
    manual = await services.manuals.get_manual(user_id, manual_id)
    if not manual:
        await query.answer("Статья не найдена", show_alert=True)
        return

    await query.message.edit_text(
        _format_manual_item(manual),
        parse_mode="HTML",
        reply_markup=manual_card_keyboard(manual_id, is_admin=is_admin),
    )
    await query.answer()


@router.callback_query(F.data == "manual:search")
async def manual_search_start(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SearchManualState.query)
    await query.message.answer("Введите запрос по заголовку/тегам/тексту:", reply_markup=CANCEL_MENU)
    await query.answer()


@router.message(SearchManualState.query)
async def manual_search_apply(message: Message, state: FSMContext, services: AppServices, user_id: int) -> None:
    query_text = (message.text or "").strip()
    items = await services.manuals.search_manuals(user_id, query_text)
    await state.clear()
    if not items:
        await message.answer("Совпадений не найдено.")
        return
    payload = [(m.id, m.title) for m in items]
    await message.answer("Результаты поиска:", reply_markup=manual_list_keyboard(payload))


@router.callback_query(F.data == "manual:add")
async def manual_add_start(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddManualStates.title)
    await query.message.answer("Заголовок статьи:", reply_markup=CANCEL_MENU)
    await query.answer()


@router.message(AddManualStates.title)
async def manual_add_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=(message.text or "").strip())
    await state.set_state(AddManualStates.category)
    await message.answer("Выберите категорию", reply_markup=manual_category_choose_keyboard())


@router.callback_query(F.data.startswith("manual:cat_pick:"))
async def manual_pick_category(query: CallbackQuery, state: FSMContext) -> None:
    category = query.data.split(":", maxsplit=2)[2]
    current = await state.get_state()
    if current not in {AddManualStates.category.state, EditManualStates.category.state}:
        await query.answer()
        return
    await state.update_data(category=category)

    if current == AddManualStates.category.state:
        await state.set_state(AddManualStates.tags)
        await query.message.answer("Теги через запятую (или '-' ): ")
    else:
        await state.set_state(EditManualStates.tags)
        await query.message.answer("Новые теги через запятую (или '-' оставить без изменений):")
    await query.answer("Выбрано")


@router.message(AddManualStates.tags)
async def manual_add_tags(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    await state.update_data(tags=[] if raw == "-" else parse_tags_input(raw))
    await state.set_state(AddManualStates.body)
    await message.answer("Текст markdown статьи:")


@router.message(AddManualStates.body)
async def manual_add_finish(message: Message, state: FSMContext, services: AppServices, user_id: int) -> None:
    data = await state.get_data()
    try:
        payload = ManualCreateSchema(
            owner_telegram_id=user_id,
            title=data["title"],
            category=MANUAL_CATEGORY_MAP[data["category"]],
            tags=data.get("tags", []),
            body_markdown=message.text or "",
        )
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"Ошибка валидации: {exc}")
        return

    manual = await services.manuals.create_manual(payload)
    await state.clear()
    await message.answer(f"Статья '{manual.title}' добавлена.")


@router.callback_query(F.data.startswith("manual:commands:"))
async def manual_commands(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    manual_id = int(query.data.split(":", maxsplit=2)[2])
    manual = await services.manuals.get_manual(user_id, manual_id)
    if not manual:
        await query.answer("Статья не найдена", show_alert=True)
        return

    commands = parse_manual_commands(manual.body_markdown)
    if not commands:
        await query.message.answer("В статье нет code block команд.")
        await query.answer()
        return

    lines = ["Команды из статьи:"]
    for idx, block in enumerate(commands, start=1):
        lines.append(f"\n#{idx}\n{block}")
    await query.message.answer("\n".join(lines))
    await query.answer()


@router.callback_query(F.data.startswith("manual:delete:"))
async def manual_delete(query: CallbackQuery, services: AppServices, user_id: int, is_admin: bool) -> None:
    if not is_admin:
        await query.answer("Только администратор", show_alert=True)
        return

    manual_id = int(query.data.split(":", maxsplit=2)[2])
    deleted = await services.manuals.delete_manual(user_id, manual_id)
    await query.answer("Удалено" if deleted else "Не найдено")
    if deleted:
        await query.message.edit_text("Статья удалена.")


@router.callback_query(F.data.startswith("manual:edit:"))
async def manual_edit_start(query: CallbackQuery, state: FSMContext, services: AppServices, user_id: int, is_admin: bool) -> None:
    if not is_admin:
        await query.answer("Только администратор", show_alert=True)
        return

    manual_id = int(query.data.split(":", maxsplit=2)[2])
    manual = await services.manuals.get_manual(user_id, manual_id)
    if not manual:
        await query.answer("Статья не найдена", show_alert=True)
        return

    await state.clear()
    await state.update_data(
        manual_id=manual_id,
        old_title=manual.title,
        old_category=manual.category.value,
        old_tags=[t.tag for t in manual.tags],
        old_body=manual.body_markdown,
    )
    await state.set_state(EditManualStates.title)
    await query.message.answer("Новый заголовок (или '-' без изменений):", reply_markup=CANCEL_MENU)
    await query.answer()


@router.message(EditManualStates.title)
async def manual_edit_title(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if value != "-":
        await state.update_data(new_title=value)
    await state.set_state(EditManualStates.category)
    await message.answer(
        "Выберите новую категорию кнопкой ниже или отправьте '-' без изменений:",
        reply_markup=manual_category_choose_keyboard(),
    )


@router.message(EditManualStates.category)
async def manual_edit_category_help(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if value == "-":
        await state.set_state(EditManualStates.tags)
        await message.answer("Новые теги через запятую (или '-' без изменений):")
        return
    await message.answer("Используйте кнопку выбора категории или отправьте '-'")


@router.message(EditManualStates.tags)
async def manual_edit_tags(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if value != "-":
        await state.update_data(new_tags=parse_tags_input(value))
    await state.set_state(EditManualStates.body)
    await message.answer("Новый markdown текст (или '-' без изменений):")


@router.message(EditManualStates.body)
async def manual_edit_finish(message: Message, state: FSMContext, services: AppServices, user_id: int) -> None:
    value = (message.text or "").strip()
    data = await state.get_data()
    title = data.get("new_title", data["old_title"])
    category = MANUAL_CATEGORY_MAP.get(data.get("category", data["old_category"]), MANUAL_CATEGORY_MAP[data["old_category"]])
    tags = data.get("new_tags", data["old_tags"])
    body = data["old_body"] if value == "-" else value

    updated = await services.manuals.update_manual(
        owner_telegram_id=user_id,
        manual_id=int(data["manual_id"]),
        title=title,
        category=category,
        tags=tags,
        body_markdown=body,
    )
    await state.clear()
    await message.answer("Статья обновлена." if updated else "Статья не найдена.")


@router.message(F.text.casefold() == "отмена")
async def manual_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current and current.startswith((AddManualStates.__name__, EditManualStates.__name__, SearchManualState.__name__)):
        await state.clear()
        await message.answer("Действие отменено.")

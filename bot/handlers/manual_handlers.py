from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.dependencies import AppServices
from bot.keyboards.main import CANCEL_MENU
from bot.keyboards.manuals import (
    add_manual_confirm_keyboard,
    manual_card_keyboard,
    manual_categories_keyboard,
    manual_category_choose_keyboard,
    manual_list_keyboard,
)
from bot.states.manual_states import EditManualStates, SearchManualState
from bot.structured_input import (
    ADD_MANUAL_TEMPLATE,
    ParsedManualInput,
    StructuredInputError,
    parse_manual_input,
)
from services.schemas import MANUAL_CATEGORY_MAP, parse_manual_commands, parse_tags_input

router = Router()

CATEGORY_TITLE = {
    "install": "Установка",
    "troubleshoot": "Диагностика",
    "upgrade": "Обновление",
    "other": "Другое",
}

PENDING_MANUAL_INPUT_USERS: set[int] = set()
PENDING_MANUAL_PREVIEWS: dict[int, ParsedManualInput] = {}


def _reset_manual_add(user_id: int) -> None:
    PENDING_MANUAL_INPUT_USERS.discard(user_id)
    PENDING_MANUAL_PREVIEWS.pop(user_id, None)


def _format_manual_item(manual) -> str:
    tags = ", ".join(f"#{t.tag}" for t in manual.tags) if manual.tags else "-"
    body = html.escape(manual.body_markdown)
    return (
        "━━━━━━━━━━━━━━━━━━\n"
        f"🧠 Название: {html.escape(manual.title)}\n"
        f"🗂 Категория: {CATEGORY_TITLE.get(manual.category.value, manual.category.value)}\n"
        f"🏷️ Теги: {html.escape(tags)}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"<pre>{body}</pre>"
    )


def _manual_preview_text(parsed: ParsedManualInput) -> str:
    manual = parsed.manual
    tags = ", ".join(manual.tags) if manual.tags else "—"
    body = html.escape(manual.body_markdown)

    return (
        "📥 Предпросмотр мануала\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🧠 Название: {html.escape(manual.title)}\n"
        f"🗂 Категория: {CATEGORY_TITLE.get(manual.category.value, manual.category.value)}\n"
        f"🏷️ Теги: {html.escape(tags)}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"<pre>{body}</pre>\n"
        "Сохранить статью?"
    )


@router.message(Command("add_manual"))
async def cmd_add_manual(message: Message) -> None:
    if not message.from_user:
        return
    _reset_manual_add(message.from_user.id)
    PENDING_MANUAL_INPUT_USERS.add(message.from_user.id)
    await message.answer(ADD_MANUAL_TEMPLATE, reply_markup=CANCEL_MENU)


@router.callback_query(F.data == "manual:add")
async def manual_add_start(query: CallbackQuery) -> None:
    if not query.from_user:
        return
    _reset_manual_add(query.from_user.id)
    PENDING_MANUAL_INPUT_USERS.add(query.from_user.id)
    await query.message.answer(ADD_MANUAL_TEMPLATE, reply_markup=CANCEL_MENU)
    await query.answer()


@router.message(lambda m: bool(m.from_user and m.from_user.id in PENDING_MANUAL_INPUT_USERS))
async def manual_add_parse_single(message: Message) -> None:
    if not message.from_user:
        return
    user_id = message.from_user.id
    text = (message.text or "").strip()

    if text.casefold() == "отмена":
        _reset_manual_add(user_id)
        await message.answer("Добавление мануала отменено.")
        return

    if text.startswith("/"):
        await message.answer("Сначала отправьте заполненный шаблон или «Отмена».")
        return

    try:
        parsed = parse_manual_input(text, user_id)
    except StructuredInputError as exc:
        errors = "\n".join(f"• {html.escape(item)}" for item in exc.errors)
        await message.answer(
            f"Не удалось разобрать шаблон:\n{errors}\n\nПроверьте формат и отправьте сообщение заново.",
            parse_mode="HTML",
        )
        return
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"Ошибка разбора: {exc}")
        return

    PENDING_MANUAL_INPUT_USERS.discard(user_id)
    PENDING_MANUAL_PREVIEWS[user_id] = parsed
    await message.answer(_manual_preview_text(parsed), parse_mode="HTML", reply_markup=add_manual_confirm_keyboard())


@router.callback_query(F.data == "manual:add:confirm")
async def manual_add_confirm(query: CallbackQuery, services: AppServices, is_admin: bool) -> None:
    if not query.from_user:
        return
    user_id = query.from_user.id
    parsed = PENDING_MANUAL_PREVIEWS.get(user_id)
    if not parsed:
        await query.answer("Нет данных для сохранения. Повторите /add_manual", show_alert=True)
        return

    try:
        manual = await services.manuals.create_manual(parsed.manual)
    except Exception as exc:  # noqa: BLE001
        await query.answer("Ошибка сохранения", show_alert=True)
        await query.message.answer(f"Не удалось сохранить статью: {exc}")
        return

    _reset_manual_add(user_id)
    manual_full = await services.manuals.get_manual(user_id, manual.id)
    if manual_full:
        await query.message.edit_text(
            _format_manual_item(manual_full),
            parse_mode="HTML",
            reply_markup=manual_card_keyboard(manual_full.id, is_admin=is_admin),
        )
    else:
        await query.message.edit_text("Статья сохранена.")
    await query.answer("Сохранено")


@router.callback_query(F.data == "manual:add:cancel")
async def manual_add_cancel(query: CallbackQuery) -> None:
    if query.from_user:
        _reset_manual_add(query.from_user.id)
    await query.message.edit_text("Добавление мануала отменено.")
    await query.answer()


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


@router.callback_query(F.data.startswith("manual:cat_pick:"))
async def manual_pick_category(query: CallbackQuery, state: FSMContext) -> None:
    category = query.data.split(":", maxsplit=2)[2]
    current = await state.get_state()
    if current != EditManualStates.category.state:
        await query.answer()
        return
    await state.update_data(category=category)
    await state.set_state(EditManualStates.tags)
    await query.message.answer("Новые теги через запятую (или '-' оставить без изменений):")
    await query.answer("Выбрано")


@router.callback_query(F.data.startswith("manual:commands:"))
async def manual_commands(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    manual_id = int(query.data.split(":", maxsplit=2)[2])
    manual = await services.manuals.get_manual(user_id, manual_id)
    if not manual:
        await query.answer("Статья не найдена", show_alert=True)
        return

    commands = parse_manual_commands(manual.body_markdown)
    if not commands:
        await query.message.answer("В статье нет блоков команд.")
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
    pending_cleared = False
    if message.from_user and message.from_user.id in PENDING_MANUAL_INPUT_USERS | set(PENDING_MANUAL_PREVIEWS.keys()):
        _reset_manual_add(message.from_user.id)
        pending_cleared = True

    current = await state.get_state()
    if current and current.startswith((EditManualStates.__name__, SearchManualState.__name__)):
        await state.clear()
        await message.answer("Действие отменено.")
        return

    if pending_cleared:
        await message.answer("Действие отменено.")

from __future__ import annotations

import html
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.dependencies import AppServices
from bot.keyboards.main import CANCEL_MENU
from bot.keyboards.vps import (
    add_server_confirm_keyboard,
    secret_confirm_keyboard,
    server_card_keyboard,
    server_list_keyboard,
    vps_menu_keyboard,
)
from bot.states.vps_states import EditLoadStates, SearchServerState
from bot.structured_input import (
    ADD_SERVER_TEMPLATE,
    ParsedServerInput,
    StructuredInputError,
    parse_server_input,
)
from bot.utils import send_temporary_secret
from db.models import ServerStatus
from services.schemas import BillingCreateSchema

router = Router()

ROLE_TITLE = {
    "bridge": "Мост",
    "xray-edge": "Xray Edge",
    "panel": "Панель",
    "db": "База данных",
    "test": "Тест",
    "other": "Другое",
}

STATUS_TITLE = {
    "active": "Активен",
    "archived": "В архиве",
}

SECRET_TYPE_TITLE = {
    "password": "Пароль",
    "private_key": "Приватный ключ",
    "none": "Нет",
}

PENDING_SERVER_INPUT_USERS: set[int] = set()
PENDING_SERVER_PREVIEWS: dict[int, ParsedServerInput] = {}


def _reset_server_add(user_id: int) -> None:
    PENDING_SERVER_INPUT_USERS.discard(user_id)
    PENDING_SERVER_PREVIEWS.pop(user_id, None)


def _format_load(value: Decimal | float | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


def _format_money(amount: object, currency: str) -> str:
    return f"{amount} {currency}".strip()


def _server_card_text(server, latest_billing) -> str:
    tag_text = ", ".join(tag.tag for tag in server.tags) if server.tags else "—"
    ssh_line = f"{server.ssh_user}@{server.ip4}:{server.ssh_port}"
    status_emoji = "🟢" if server.status == ServerStatus.ACTIVE else "🟡"

    if latest_billing:
        pay_amount = _format_money(latest_billing.price_amount, latest_billing.price_currency)
        pay_expires = latest_billing.expires_at.strftime("%Y-%m-%d")
    else:
        pay_amount = "—"
        pay_expires = "—"

    notes = html.escape(server.notes or "—")
    net_notes = html.escape(server.net_notes or "—")

    return (
        "━━━━━━━━━━━━━━━━━━\n"
        f"🖥️ Название: {html.escape(server.name)}\n"
        f"🧩 Роль: {ROLE_TITLE.get(server.role.value, server.role.value)}\n"
        f"🏢 Провайдер: {html.escape(server.provider)}\n\n"
        f"🌍 IPv4: {html.escape(server.ip4)}\n"
        f"🌐 IPv6: {html.escape(server.ip6 or '—')}\n"
        f"🔗 Домен: {html.escape(server.domain or '—')}\n\n"
        f"🔐 SSH: {html.escape(ssh_line)}\n"
        f"🏷️ Теги: {html.escape(tag_text)}\n"
        f"📝 Заметки: {notes}\n"
        f"📊 Нагрузка CPU/RAM/DISK: {_format_load(server.cpu_load)} / {_format_load(server.ram_load)} / {_format_load(server.disk_load)}\n"
        f"🌐 Сеть: {net_notes}\n\n"
        "💰 Последняя оплата:\n"
        f"   Сумма: {html.escape(pay_amount)}\n"
        f"   Истекает: {pay_expires}\n\n"
        f"Статус: {status_emoji} {STATUS_TITLE.get(server.status.value, server.status.value)}\n"
        "━━━━━━━━━━━━━━━━━━"
    )


def _server_preview_text(parsed: ParsedServerInput) -> str:
    server = parsed.server
    billing = parsed.billing
    secret_mask = "••••••••" if server.secret_type.value != "none" and server.secret_value else "—"
    tags = ", ".join(server.tags) if server.tags else "—"

    return (
        "📥 Предпросмотр нового сервера\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🖥️ Название: {html.escape(server.name)}\n"
        f"🧩 Роль: {ROLE_TITLE.get(server.role.value, server.role.value)}\n"
        f"🏢 Провайдер: {html.escape(server.provider)}\n\n"
        f"🌍 IPv4: {html.escape(server.ip4)}\n"
        f"🌐 IPv6: {html.escape(server.ip6 or '—')}\n"
        f"🔗 Домен: {html.escape(server.domain or '—')}\n"
        f"🔐 SSH: {html.escape(f'{server.ssh_user}@{server.ip4}:{server.ssh_port}')}\n"
        f"🔒 Тип секрета: {SECRET_TYPE_TITLE.get(server.secret_type.value, server.secret_type.value)}\n"
        f"🔒 Секрет: {secret_mask}\n"
        f"🏷️ Теги: {html.escape(tags)}\n"
        f"📝 Заметки: {html.escape(server.notes or '—')}\n\n"
        "💰 Оплата:\n"
        f"   Дата оплаты: {billing.paid_at.isoformat()}\n"
        f"   Дата истечения: {billing.expires_at.isoformat()}\n"
        f"   Сумма: {html.escape(_format_money(billing.amount, billing.currency))}\n"
        f"   Период: {html.escape(billing.period)}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Сохранить запись?"
    )


async def _render_server_card(query: CallbackQuery, services: AppServices, user_id: int, server_id: str) -> None:
    server = await services.servers.get_server(user_id, server_id)
    if not server:
        await query.answer("Сервер не найден", show_alert=True)
        return

    latest_billing = await services.billing.latest_billing_for_server(server.id)
    await query.message.edit_text(
        _server_card_text(server, latest_billing),
        parse_mode="HTML",
        reply_markup=server_card_keyboard(str(server.id), server.status == ServerStatus.ARCHIVED, server.is_favorite),
    )


@router.message(Command("add_server"))
async def cmd_add_server(message: Message) -> None:
    if not message.from_user:
        return
    _reset_server_add(message.from_user.id)
    PENDING_SERVER_INPUT_USERS.add(message.from_user.id)
    await message.answer(ADD_SERVER_TEMPLATE, reply_markup=CANCEL_MENU)


@router.callback_query(F.data == "vps:add")
async def vps_add_start(query: CallbackQuery) -> None:
    if not query.from_user:
        return
    _reset_server_add(query.from_user.id)
    PENDING_SERVER_INPUT_USERS.add(query.from_user.id)
    await query.message.answer(ADD_SERVER_TEMPLATE, reply_markup=CANCEL_MENU)
    await query.answer()


@router.message(lambda m: bool(m.from_user and m.from_user.id in PENDING_SERVER_INPUT_USERS))
async def vps_add_parse_single(message: Message) -> None:
    if not message.from_user:
        return
    user_id = message.from_user.id
    text = (message.text or "").strip()

    if text.casefold() == "отмена":
        _reset_server_add(user_id)
        await message.answer("Добавление сервера отменено.")
        return

    if text.startswith("/"):
        await message.answer("Сначала завершите ввод по шаблону или отправьте «Отмена».")
        return

    try:
        parsed = parse_server_input(text, user_id)
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

    PENDING_SERVER_INPUT_USERS.discard(user_id)
    PENDING_SERVER_PREVIEWS[user_id] = parsed
    await message.answer(_server_preview_text(parsed), parse_mode="HTML", reply_markup=add_server_confirm_keyboard())


@router.callback_query(F.data == "vps:add:confirm")
async def vps_add_confirm(query: CallbackQuery, services: AppServices) -> None:
    if not query.from_user:
        return
    user_id = query.from_user.id
    parsed = PENDING_SERVER_PREVIEWS.get(user_id)
    if not parsed:
        await query.answer("Нет данных для сохранения. Повторите /add_server", show_alert=True)
        return

    try:
        server = await services.servers.create_server(parsed.server)
        await services.billing.add_billing(
            BillingCreateSchema(
                server_id=str(server.id),
                paid_at=parsed.billing.paid_at,
                expires_at=parsed.billing.expires_at,
                price_amount=parsed.billing.amount,
                price_currency=parsed.billing.currency,
                period=parsed.billing.period,
                comment=parsed.billing.comment,
            )
        )
    except Exception as exc:  # noqa: BLE001
        await query.answer("Ошибка сохранения", show_alert=True)
        await query.message.answer(f"Не удалось сохранить данные: {exc}")
        return

    _reset_server_add(user_id)
    refreshed = await services.servers.get_server(user_id, str(server.id))
    latest_billing = await services.billing.latest_billing_for_server(server.id)
    if refreshed:
        await query.message.edit_text(
            _server_card_text(refreshed, latest_billing),
            parse_mode="HTML",
            reply_markup=server_card_keyboard(str(refreshed.id), refreshed.status == ServerStatus.ARCHIVED, refreshed.is_favorite),
        )
    else:
        await query.message.edit_text("Сервер сохранен.")
    await query.answer("Сохранено")


@router.callback_query(F.data == "vps:add:cancel")
async def vps_add_cancel(query: CallbackQuery) -> None:
    if query.from_user:
        _reset_server_add(query.from_user.id)
    await query.message.edit_text("Добавление сервера отменено.")
    await query.answer()


@router.callback_query(F.data == "vps:search")
async def vps_search_start(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SearchServerState.query)
    await query.message.answer("Введите строку поиска (имя/IP/роль/провайдер/тег):", reply_markup=CANCEL_MENU)
    await query.answer()


@router.message(SearchServerState.query)
async def vps_search_apply(message: Message, state: FSMContext, services: AppServices, user_id: int) -> None:
    query_text = message.text or ""
    servers, total = await services.servers.list_servers(user_id, page=1, search=query_text)
    await state.clear()
    if not servers:
        await message.answer("Ничего не найдено.")
        return
    items = [(str(s.id), f"{s.name} ({s.ip4})") for s in servers]
    await message.answer(f"Найдено: {total}", reply_markup=server_list_keyboard(items, 1, total))


@router.callback_query(F.data.startswith("vps:filter:"))
async def vps_filter(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    mode = query.data.split(":", maxsplit=2)[2]
    if mode == "favorites":
        servers, _ = await services.servers.list_servers(user_id, scope="all", page_size=100)
        servers = [s for s in servers if s.is_favorite]
        if not servers:
            await query.message.edit_text("Избранных серверов нет.", reply_markup=vps_menu_keyboard())
            await query.answer()
            return
        items = [(str(s.id), f"⭐ {s.name} ({s.ip4})") for s in servers]
        await query.message.edit_text("Избранные серверы:", reply_markup=server_list_keyboard(items, 1, len(items), page_size=max(1, len(items))))
        await query.answer()
        return

    scope = mode if mode in {"active", "archived", "expiring_7"} else "all"
    servers, total = await services.servers.list_servers(user_id, page=1, scope=scope)
    if not servers:
        await query.message.edit_text("Список пуст.", reply_markup=vps_menu_keyboard())
        await query.answer()
        return

    items = [(str(s.id), f"{s.name} ({s.ip4})") for s in servers]
    await query.message.edit_text("Результат фильтра:", reply_markup=server_list_keyboard(items, 1, total))
    await query.answer()


@router.callback_query(F.data.startswith("vps:list:"))
async def vps_list(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    page = int(query.data.split(":")[2])
    servers, total = await services.servers.list_servers(user_id, page=page)
    if not servers:
        await query.message.edit_text("Серверов пока нет.", reply_markup=vps_menu_keyboard())
        await query.answer()
        return

    items = [(str(s.id), f"{'⭐ ' if s.is_favorite else ''}{s.name} ({s.ip4})") for s in servers]
    await query.message.edit_text("Список серверов:", reply_markup=server_list_keyboard(items, page, total))
    await query.answer()


@router.callback_query(F.data.startswith("vps:card:"))
async def vps_card(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    server_id = query.data.split(":", maxsplit=2)[2]
    await _render_server_card(query, services, user_id, server_id)
    await query.answer()


@router.callback_query(F.data.startswith("vps:copy_ip:"))
async def vps_copy_ip(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    server_id = query.data.split(":", maxsplit=2)[2]
    server = await services.servers.get_server(user_id, server_id)
    if not server:
        await query.answer("Сервер не найден", show_alert=True)
        return
    await query.message.answer(f"IP для копирования:\n<code>{server.ip4}</code>", parse_mode="HTML")
    await query.answer("Отправил")


@router.callback_query(F.data.startswith("vps:copy_ssh:"))
async def vps_copy_ssh(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    server_id = query.data.split(":", maxsplit=2)[2]
    server = await services.servers.get_server(user_id, server_id)
    if not server:
        await query.answer("Сервер не найден", show_alert=True)
        return
    cmd = f"ssh {server.ssh_user}@{server.ip4} -p {server.ssh_port}"
    await query.message.answer(f"SSH для копирования:\n<code>{cmd}</code>", parse_mode="HTML")
    await query.answer("Отправил")


@router.callback_query(F.data.startswith("vps:copy_all:"))
async def vps_copy_all(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    server_id = query.data.split(":", maxsplit=2)[2]
    server = await services.servers.get_server(user_id, server_id)
    if not server:
        await query.answer("Сервер не найден", show_alert=True)
        return
    block = services.servers.build_copy_block(server)
    await query.message.answer(f"<pre>{block}</pre>", parse_mode="HTML")
    await query.answer("Отправил")


@router.callback_query(F.data.startswith("vps:secret_ask:"))
async def vps_secret_ask(query: CallbackQuery) -> None:
    server_id = query.data.split(":", maxsplit=2)[2]
    await query.message.answer("Показать секрет? Сообщение будет удалено автоматически.", reply_markup=secret_confirm_keyboard(server_id))
    await query.answer()


@router.callback_query(F.data.startswith("vps:secret_show:"))
async def vps_secret_show(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    server_id = query.data.split(":", maxsplit=2)[2]
    secret = await services.servers.reveal_secret(user_id, server_id)
    if not secret:
        await query.answer("Секрет не задан", show_alert=True)
        return
    ttl = await services.settings.get_secret_ttl()
    await send_temporary_secret(query.bot, query.message.chat.id, f"🔐 Секрет:\n<code>{secret}</code>", ttl_seconds=ttl)
    await query.answer(f"Показано на {ttl} сек")


@router.callback_query(F.data.startswith("vps:archive:"))
async def vps_archive_toggle(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    server_id = query.data.split(":", maxsplit=2)[2]
    result = await services.servers.toggle_archive(user_id, server_id)
    if not result:
        await query.answer("Сервер не найден", show_alert=True)
        return
    await _render_server_card(query, services, user_id, server_id)
    await query.answer("Статус изменён")


@router.callback_query(F.data.startswith("vps:favorite:"))
async def vps_favorite_toggle(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    server_id = query.data.split(":", maxsplit=2)[2]
    result = await services.servers.toggle_favorite(user_id, server_id)
    if not result:
        await query.answer("Сервер не найден", show_alert=True)
        return
    await _render_server_card(query, services, user_id, server_id)
    await query.answer("Обновлено")


@router.callback_query(F.data.startswith("vps:edit_load:"))
async def vps_edit_load_start(query: CallbackQuery, state: FSMContext) -> None:
    server_id = query.data.split(":", maxsplit=2)[2]
    await state.update_data(server_id=server_id)
    await state.set_state(EditLoadStates.notes)
    await query.message.answer("Введите заметки (или '-' чтобы оставить пусто):", reply_markup=CANCEL_MENU)
    await query.answer()


@router.message(EditLoadStates.notes)
async def vps_edit_load_notes(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    await state.update_data(notes="" if value == "-" else value)
    await state.set_state(EditLoadStates.cpu)
    await message.answer("CPU % (например 12.5 или '-'): ")


@router.message(EditLoadStates.cpu)
async def vps_edit_load_cpu(message: Message, state: FSMContext) -> None:
    await state.update_data(cpu=None if (message.text or "").strip() == "-" else (message.text or "").strip())
    await state.set_state(EditLoadStates.ram)
    await message.answer("RAM % (например 34.7 или '-'): ")


@router.message(EditLoadStates.ram)
async def vps_edit_load_ram(message: Message, state: FSMContext) -> None:
    await state.update_data(ram=None if (message.text or "").strip() == "-" else (message.text or "").strip())
    await state.set_state(EditLoadStates.disk)
    await message.answer("DISK % (например 70.1 или '-'): ")


@router.message(EditLoadStates.disk)
async def vps_edit_load_disk(message: Message, state: FSMContext) -> None:
    await state.update_data(disk=None if (message.text or "").strip() == "-" else (message.text or "").strip())
    await state.set_state(EditLoadStates.net_notes)
    await message.answer("Заметка по сети (или '-'): ")


@router.message(EditLoadStates.net_notes)
async def vps_edit_load_finish(message: Message, state: FSMContext, services: AppServices, user_id: int) -> None:
    payload = await state.get_data()
    net_notes = (message.text or "").strip()
    net_notes = None if net_notes == "-" else net_notes

    def parse_optional_float(value: str | None) -> float | None:
        if value in (None, ""):
            return None
        return float(str(value).replace(",", "."))

    try:
        ok = await services.servers.update_server_notes_and_load(
            owner_telegram_id=user_id,
            server_id=payload["server_id"],
            notes=payload.get("notes", ""),
            cpu_load=parse_optional_float(payload.get("cpu")),
            ram_load=parse_optional_float(payload.get("ram")),
            disk_load=parse_optional_float(payload.get("disk")),
            net_notes=net_notes,
        )
    except ValueError:
        await message.answer("Ошибка формата нагрузки. Используйте число или '-'.")
        return

    await state.clear()
    await message.answer("Данные обновлены." if ok else "Сервер не найден.")


@router.message(F.text.casefold() == "отмена")
async def common_cancel(message: Message, state: FSMContext) -> None:
    pending_cleared = False
    if message.from_user and message.from_user.id in PENDING_SERVER_INPUT_USERS | set(PENDING_SERVER_PREVIEWS.keys()):
        _reset_server_add(message.from_user.id)
        pending_cleared = True

    if await state.get_state() is not None:
        await state.clear()
        await message.answer("Действие отменено.")
        return

    if pending_cleared:
        await message.answer("Действие отменено.")

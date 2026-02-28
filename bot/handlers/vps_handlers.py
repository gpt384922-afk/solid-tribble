from __future__ import annotations

import html
from datetime import date
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.dependencies import AppServices
from bot.keyboards.main import CANCEL_MENU
from bot.keyboards.vps import (
    add_server_confirm_keyboard,
    delete_confirm_keyboard,
    expiring_menu_keyboard,
    server_card_keyboard,
    server_list_keyboard,
    vps_menu_keyboard,
)
from bot.states.vps_states import AddServerStates, SearchServerState
from db.models import ServerRole
from services.schemas import BillingCreateSchema, SECRET_TYPE_MAP, ServerCreateSchema

router = Router()
PAGE_SIZE = 5


def _opt(value: str) -> str | None:
    cleaned = value.strip()
    if cleaned in {"", "-", "—"}:
        return None
    return cleaned


def _parse_iso_date(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"{label}: используйте формат YYYY-MM-DD") from exc


def _parse_amount_with_currency(value: str) -> tuple[str, str]:
    raw = value.strip()
    parts = raw.split()
    if len(parts) == 1:
        amount_raw = parts[0]
        currency = "EUR"
    elif len(parts) == 2:
        amount_raw = parts[0]
        currency = parts[1].upper()
    else:
        raise ValueError("Сумма: используйте формат '10' или '10 EUR'")

    try:
        amount = Decimal(amount_raw.replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError("Сумма должна быть числом") from exc

    if amount <= 0:
        raise ValueError("Сумма должна быть больше 0")

    return str(amount), currency


def _derive_period(paid_at: date, expires_at: date) -> str:
    days = (expires_at - paid_at).days
    return f"{days}d" if days > 0 else "custom"


def _preview_text(data: dict[str, str]) -> str:
    domain = data.get("domain") or "—"
    return (
        "Проверьте перед сохранением:\n"
        "━━━━━━━━━━━━━━━━\n"
        f"🖥 {html.escape(data['name'])}\n"
        f"🏢 {html.escape(data['provider'])}\n"
        f"🌍 {html.escape(data['ip4'])}\n"
        f"🔗 {html.escape(domain)}\n\n"
        f"🔐 SSH: {html.escape(data['ssh_user'])}@{html.escape(data['ip4'])}\n"
        f"💰 {html.escape(data['amount'])} {html.escape(data['currency'])}\n"
        f"📅 До: {html.escape(data['expires_at'])}\n"
        "━━━━━━━━━━━━━━━━"
    )


def _status_marker(expires_at: date | None) -> tuple[str, str]:
    if expires_at is None:
        return "⚪", "📅 Нет даты"

    days_left = (expires_at - date.today()).days
    if days_left <= 1:
        if days_left < 0:
            return "🔴", "⚠ Просрочен"
        if days_left == 0:
            return "🔴", "⚠ Истекает сегодня"
        return "🔴", "⚠ Истекает завтра"
    if days_left <= 14:
        return "🟡", f"⚠ {days_left} дней"
    return "🟢", f"📅 До {expires_at.strftime('%d.%m.%Y')}"


def _server_card_text(server, latest_billing) -> str:
    domain = server.domain or "—"
    if latest_billing:
        amount = f"{latest_billing.price_amount} {latest_billing.price_currency}"
        expires = latest_billing.expires_at.strftime("%d.%m.%Y")
    else:
        amount = "—"
        expires = "—"

    return (
        "━━━━━━━━━━━━━━━━\n"
        f"🖥 {html.escape(server.name)}\n"
        f"🏢 {html.escape(server.provider)}\n\n"
        f"🌍 {html.escape(server.ip4)}\n"
        f"🔗 {html.escape(domain)}\n\n"
        f"🔐 SSH: {html.escape(server.ssh_user)}@{html.escape(server.ip4)}\n\n"
        f"💰 {html.escape(amount)}\n"
        f"📅 До: {html.escape(expires)}\n"
        "━━━━━━━━━━━━━━━━"
    )


async def _format_server_list_blocks(services: AppServices, servers: list) -> tuple[list[str], list[tuple[str, str]]]:
    blocks: list[str] = []
    buttons: list[tuple[str, str]] = []

    for server in servers:
        nearest = await services.billing.nearest_billing_for_server(server.id)
        expires = nearest.expires_at if nearest else None
        emoji, line3 = _status_marker(expires)

        blocks.append(
            f"{emoji} {html.escape(server.name)}\n"
            f"🌍 {html.escape(server.ip4)}\n"
            f"{line3}"
        )
        buttons.append((str(server.id), f"{emoji} {server.name}"))

    return blocks, buttons


def _join_cards(title: str, blocks: list[str]) -> str:
    if not blocks:
        return f"{title}\n━━━━━━━━━━━━━━━━\nПусто"

    parts = [title, "━━━━━━━━━━━━━━━━"]
    for index, block in enumerate(blocks):
        parts.append(block)
        if index != len(blocks) - 1:
            parts.append("━━━━━━━━━━━━━━━━")
    return "\n".join(parts)


async def _render_server_card(query: CallbackQuery, services: AppServices, user_id: int, server_id: str) -> None:
    server = await services.servers.get_server(user_id, server_id)
    if not server:
        await query.answer("Сервер не найден", show_alert=True)
        return

    latest_billing = await services.billing.latest_billing_for_server(server.id)
    await query.message.edit_text(
        _server_card_text(server, latest_billing),
        parse_mode="HTML",
        reply_markup=server_card_keyboard(str(server.id)),
    )


async def _start_add_flow(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddServerStates.name)
    await message.answer("1/10 Название сервера?", reply_markup=CANCEL_MENU)


@router.message(Command("add_server"))
async def cmd_add_server(message: Message, state: FSMContext) -> None:
    await _start_add_flow(message, state)


@router.callback_query(F.data == "vps:add")
async def vps_add_start(query: CallbackQuery, state: FSMContext) -> None:
    await _start_add_flow(query.message, state)
    await query.answer()


@router.message(AddServerStates.name)
async def add_server_name(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not value:
        await message.answer("Название не может быть пустым.")
        return
    await state.update_data(name=value)
    await state.set_state(AddServerStates.provider)
    await message.answer("2/10 Провайдер?")


@router.message(AddServerStates.provider)
async def add_server_provider(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not value:
        await message.answer("Провайдер не может быть пустым.")
        return
    await state.update_data(provider=value)
    await state.set_state(AddServerStates.ip4)
    await message.answer("3/10 IPv4?")


@router.message(AddServerStates.ip4)
async def add_server_ip4(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    await state.update_data(ip4=value)
    await state.set_state(AddServerStates.domain)
    await message.answer("4/10 Домен? (или '-')")


@router.message(AddServerStates.domain)
async def add_server_domain(message: Message, state: FSMContext) -> None:
    value = _opt(message.text or "")
    await state.update_data(domain=value)
    await state.set_state(AddServerStates.ssh_user)
    await message.answer("5/10 SSH пользователь?")


@router.message(AddServerStates.ssh_user)
async def add_server_ssh_user(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not value:
        await message.answer("SSH пользователь не может быть пустым.")
        return
    await state.update_data(ssh_user=value)
    await state.set_state(AddServerStates.secret_type)
    await message.answer("6/10 Тип секрета: password/private_key/none")


@router.message(AddServerStates.secret_type)
async def add_server_secret_type(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip().lower()
    if value not in SECRET_TYPE_MAP:
        await message.answer("Допустимо только: password/private_key/none")
        return
    await state.update_data(secret_type=value)
    await state.set_state(AddServerStates.secret_value)
    await message.answer("7/10 Секрет? (если none, отправьте '-')")


@router.message(AddServerStates.secret_value)
async def add_server_secret_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    secret_type = data["secret_type"]
    secret = _opt(message.text or "")

    if secret_type != "none" and not secret:
        await message.answer("Для выбранного типа секрета поле обязательно.")
        return

    await state.update_data(secret_value=secret)
    await state.set_state(AddServerStates.paid_at)
    await message.answer("8/10 Дата оплаты (YYYY-MM-DD)?")


@router.message(AddServerStates.paid_at)
async def add_server_paid_at(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    try:
        _parse_iso_date(value, "Дата оплаты")
    except ValueError as exc:
        await message.answer(str(exc))
        return

    await state.update_data(paid_at=value)
    await state.set_state(AddServerStates.expires_at)
    await message.answer("9/10 Дата истечения (YYYY-MM-DD)?")


@router.message(AddServerStates.expires_at)
async def add_server_expires_at(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    try:
        _parse_iso_date(value, "Дата истечения")
    except ValueError as exc:
        await message.answer(str(exc))
        return

    await state.update_data(expires_at=value)
    await state.set_state(AddServerStates.amount)
    await message.answer("10/10 Сумма? (например: 10 или 10 EUR)")


@router.message(AddServerStates.amount)
async def add_server_amount(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    try:
        amount, currency = _parse_amount_with_currency(raw)
    except ValueError as exc:
        await message.answer(str(exc))
        return

    data = await state.get_data()
    await state.update_data(amount=amount, currency=currency)

    preview_data = {
        "name": data["name"],
        "provider": data["provider"],
        "ip4": data["ip4"],
        "domain": data.get("domain") or "—",
        "ssh_user": data["ssh_user"],
        "amount": amount,
        "currency": currency,
        "expires_at": data["expires_at"],
    }

    await state.set_state(AddServerStates.confirm)
    await message.answer(_preview_text(preview_data), parse_mode="HTML", reply_markup=add_server_confirm_keyboard())


@router.callback_query(F.data == "vps:add:confirm")
async def add_server_confirm(query: CallbackQuery, state: FSMContext, services: AppServices) -> None:
    if not query.from_user:
        await query.answer("Пользователь не определен", show_alert=True)
        return

    data = await state.get_data()
    if not data:
        await query.answer("Нет данных для сохранения. Начните заново: /add_server", show_alert=True)
        return

    try:
        paid_at = _parse_iso_date(data["paid_at"], "Дата оплаты")
        expires_at = _parse_iso_date(data["expires_at"], "Дата истечения")
        if expires_at < paid_at:
            await query.answer("Дата истечения раньше даты оплаты", show_alert=True)
            return

        server_payload = ServerCreateSchema(
            owner_telegram_id=query.from_user.id,
            name=data["name"],
            role=ServerRole.OTHER,
            provider=data["provider"],
            ip4=data["ip4"],
            ip6=None,
            domain=data.get("domain"),
            ssh_port=22,
            ssh_user=data["ssh_user"],
            secret_type=SECRET_TYPE_MAP[data["secret_type"]],
            secret_value=data.get("secret_value"),
            tags=[],
            notes="",
        )
        server = await services.servers.create_server(server_payload)

        period = _derive_period(paid_at, expires_at)
        await services.billing.add_billing(
            BillingCreateSchema(
                server_id=str(server.id),
                paid_at=paid_at,
                expires_at=expires_at,
                price_amount=data["amount"],
                price_currency=data["currency"],
                period=period,
                comment=None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        await query.answer("Ошибка сохранения", show_alert=True)
        await query.message.answer(f"Не удалось сохранить сервер: {exc}")
        return

    await state.clear()
    refreshed = await services.servers.get_server(query.from_user.id, str(server.id))
    latest_billing = await services.billing.latest_billing_for_server(server.id)

    if refreshed:
        await query.message.edit_text(
            _server_card_text(refreshed, latest_billing),
            parse_mode="HTML",
            reply_markup=server_card_keyboard(str(refreshed.id)),
        )
    else:
        await query.message.edit_text("Сервер сохранен.")

    await query.answer("Готово")


@router.callback_query(F.data == "vps:add:cancel")
async def add_server_cancel(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await query.message.edit_text("Добавление сервера отменено.")
    await query.answer()


@router.callback_query(F.data == "vps:search")
async def vps_search_start(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SearchServerState.query)
    await query.message.answer("Введите строку поиска:", reply_markup=CANCEL_MENU)
    await query.answer()


@router.message(SearchServerState.query)
async def vps_search_apply(message: Message, state: FSMContext, services: AppServices, user_id: int) -> None:
    query_text = (message.text or "").strip()
    servers, total = await services.servers.list_servers(user_id, page=1, search=query_text, page_size=PAGE_SIZE)
    await state.clear()
    if not servers:
        await message.answer("Ничего не найдено.")
        return

    blocks, buttons = await _format_server_list_blocks(services, servers)
    await message.answer(
        _join_cards("🔎 Результаты", blocks),
        parse_mode="HTML",
        reply_markup=server_list_keyboard(buttons, 1, total, page_size=max(total, 1)),
    )


@router.callback_query(F.data == "vps:expiring_menu")
async def vps_expiring_menu(query: CallbackQuery) -> None:
    await query.message.edit_text("⏰ Истекают", reply_markup=expiring_menu_keyboard())
    await query.answer()


@router.callback_query(F.data.startswith("vps:expiring:"))
async def vps_expiring(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    days = int(query.data.split(":", maxsplit=2)[2])
    rows = await services.billing.list_expiring(user_id, days)

    if not rows:
        title = "⚠ В 7 дней" if days == 7 else "📆 В 30 дней"
        await query.message.edit_text(f"{title}\n━━━━━━━━━━━━━━━━\nПусто", reply_markup=expiring_menu_keyboard())
        await query.answer()
        return

    cards: list[str] = []
    for server, billing, delta in rows:
        day_word = "день" if delta == 1 else "дней"
        cards.append(
            f"🖥 {html.escape(server.name)}\n"
            f"📅 {billing.expires_at.strftime('%d.%m.%Y')}\n"
            f"⏳ {delta} {day_word}\n"
            f"💰 {billing.price_amount} {billing.price_currency}"
        )

    title = "⚠ В 7 дней" if days == 7 else "📆 В 30 дней"
    await query.message.edit_text(_join_cards(title, cards), parse_mode="HTML", reply_markup=expiring_menu_keyboard())
    await query.answer()


@router.callback_query(F.data == "vps:filter:favorites")
async def vps_favorites(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    servers, _ = await services.servers.list_servers(user_id, page=1, page_size=200)
    favorites = [srv for srv in servers if srv.is_favorite]

    if not favorites:
        await query.message.edit_text("⭐ Избранное\n━━━━━━━━━━━━━━━━\nПусто", reply_markup=vps_menu_keyboard())
        await query.answer()
        return

    blocks, buttons = await _format_server_list_blocks(services, favorites)
    await query.message.edit_text(
        _join_cards("⭐ Избранное", blocks),
        parse_mode="HTML",
        reply_markup=server_list_keyboard(buttons, 1, len(favorites), page_size=max(len(favorites), 1)),
    )
    await query.answer()


@router.callback_query(F.data.startswith("vps:list:"))
async def vps_list(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    page = int(query.data.split(":", maxsplit=2)[2])
    servers, total = await services.servers.list_servers(user_id, page=page, page_size=PAGE_SIZE)
    if not servers:
        await query.message.edit_text("📋 Список серверов\n━━━━━━━━━━━━━━━━\nПусто", reply_markup=vps_menu_keyboard())
        await query.answer()
        return

    blocks, buttons = await _format_server_list_blocks(services, servers)
    await query.message.edit_text(
        _join_cards("📋 Список серверов", blocks),
        parse_mode="HTML",
        reply_markup=server_list_keyboard(buttons, page, total, page_size=PAGE_SIZE),
    )
    await query.answer()


@router.callback_query(F.data.startswith("vps:card:"))
async def vps_card(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    server_id = query.data.split(":", maxsplit=2)[2]
    await _render_server_card(query, services, user_id, server_id)
    await query.answer()


@router.callback_query(F.data.startswith("vps:delete_ask:"))
async def vps_delete_ask(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    server_id = query.data.split(":", maxsplit=2)[2]
    server = await services.servers.get_server(user_id, server_id)
    if not server:
        await query.answer("Сервер не найден", show_alert=True)
        return

    await query.message.edit_text(
        f"Вы уверены, что хотите удалить сервер {html.escape(server.name)}? Это действие необратимо.",
        parse_mode="HTML",
        reply_markup=delete_confirm_keyboard(server_id),
    )
    await query.answer()


@router.callback_query(F.data.startswith("vps:delete_confirm:"))
async def vps_delete_confirm(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    server_id = query.data.split(":", maxsplit=2)[2]
    try:
        deleted_name = await services.servers.delete_server(user_id, server_id)
    except Exception as exc:  # noqa: BLE001
        await query.answer("Ошибка удаления", show_alert=True)
        await query.message.answer(f"Не удалось удалить сервер: {exc}")
        return

    if not deleted_name:
        await query.answer("Сервер не найден", show_alert=True)
        return

    await query.message.edit_text(f"Сервер {html.escape(deleted_name)} успешно удалён.", parse_mode="HTML")
    await query.answer("Удалено")


@router.callback_query(F.data.startswith("vps:delete_cancel:"))
async def vps_delete_cancel(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    server_id = query.data.split(":", maxsplit=2)[2]
    await _render_server_card(query, services, user_id, server_id)
    await query.answer("Отменено")


@router.message(F.text.casefold() == "отмена")
async def common_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if not current:
        return

    if current.startswith((AddServerStates.__name__, SearchServerState.__name__)):
        await state.clear()
        await message.answer("Действие отменено.")

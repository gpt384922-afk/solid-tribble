from __future__ import annotations

from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.dependencies import AppServices
from bot.keyboards.main import CANCEL_MENU
from bot.keyboards.vps import (
    secret_confirm_keyboard,
    server_card_keyboard,
    server_list_keyboard,
    vps_menu_keyboard,
)
from bot.states.vps_states import AddServerStates, EditLoadStates, SearchServerState
from bot.utils import send_temporary_secret
from db.models import SecretType, ServerStatus
from services.schemas import ROLE_MAP, SECRET_TYPE_MAP, ServerCreateSchema, parse_tags_input

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
    "active": "Активный",
    "archived": "В архиве",
}

SECRET_TYPE_TITLE = {
    "password": "Пароль",
    "private_key": "Приватный ключ",
    "none": "Нет",
}


def _format_load(value: Decimal | float | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


async def _render_server_card(query: CallbackQuery, services: AppServices, user_id: int, server_id: str) -> None:
    server = await services.servers.get_server(user_id, server_id)
    if not server:
        await query.answer("Сервер не найден", show_alert=True)
        return

    nearest = await services.billing.nearest_billing_for_server(server.id)
    billing_line = "Нет записей"
    if nearest:
        billing_line = f"{nearest.expires_at.strftime('%d.%m.%Y')} | {nearest.price_amount} {nearest.price_currency}"

    ssh_cmd = f"ssh {server.ssh_user}@{server.ip4} -p {server.ssh_port}"
    text = (
        f"<b>{server.name}</b>\n"
        f"Роль: <code>{ROLE_TITLE.get(server.role.value, server.role.value)}</code>\n"
        f"Провайдер: <code>{server.provider}</code>\n"
        f"IPv4: <code>{server.ip4}</code>\n"
        f"IPv6: <code>{server.ip6 or '-'}</code>\n"
        f"Домен: <code>{server.domain or '-'}</code>\n"
        f"SSH: <code>{ssh_cmd}</code>\n"
        f"Тип секрета: <code>{SECRET_TYPE_TITLE.get(server.secret_type.value, server.secret_type.value)}</code>\n"
        f"Теги: {services.servers.tags_as_text(server.tags)}\n"
        f"Статус: <code>{STATUS_TITLE.get(server.status.value, server.status.value)}</code>\n"
        f"Ближайшее истечение: <code>{billing_line}</code>\n"
        f"Нагрузка CPU/RAM/DISK: <code>{_format_load(server.cpu_load)} / {_format_load(server.ram_load)} / {_format_load(server.disk_load)}</code>\n"
        f"Заметка по сети: <code>{server.net_notes or '-'}</code>\n"
        f"Заметки:\n{server.notes or '-'}"
    )
    await query.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=server_card_keyboard(str(server.id), server.status == ServerStatus.ARCHIVED, server.is_favorite),
    )


@router.callback_query(F.data == "vps:add")
async def vps_add_start(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddServerStates.name)
    await query.message.answer("Введите имя сервера:", reply_markup=CANCEL_MENU)
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
    if await state.get_state() is not None:
        await state.clear()
        await message.answer("Действие отменено.")


@router.message(AddServerStates.name)
async def add_server_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=(message.text or "").strip())
    await state.set_state(AddServerStates.role)
    await message.answer("Роль (bridge/xray-edge/panel/db/test/other):")


@router.message(AddServerStates.role)
async def add_server_role(message: Message, state: FSMContext) -> None:
    role_key = (message.text or "").strip().lower()
    if role_key not in ROLE_MAP:
        await message.answer("Некорректная роль. Допустимо: bridge/xray-edge/panel/db/test/other")
        return
    await state.update_data(role=role_key)
    await state.set_state(AddServerStates.provider)
    await message.answer("Провайдер:")


@router.message(AddServerStates.provider)
async def add_server_provider(message: Message, state: FSMContext) -> None:
    await state.update_data(provider=(message.text or "").strip())
    await state.set_state(AddServerStates.ip4)
    await message.answer("Введите IPv4:")


@router.message(AddServerStates.ip4)
async def add_server_ip4(message: Message, state: FSMContext) -> None:
    await state.update_data(ip4=(message.text or "").strip())
    await state.set_state(AddServerStates.ip6)
    await message.answer("Введите IPv6 (или '-' если нет):")


@router.message(AddServerStates.ip6)
async def add_server_ip6(message: Message, state: FSMContext) -> None:
    ip6 = (message.text or "").strip()
    await state.update_data(ip6=None if ip6 == "-" else ip6)
    await state.set_state(AddServerStates.domain)
    await message.answer("Домен (или '-' если нет):")


@router.message(AddServerStates.domain)
async def add_server_domain(message: Message, state: FSMContext) -> None:
    domain = (message.text or "").strip()
    await state.update_data(domain=None if domain == "-" else domain)
    await state.set_state(AddServerStates.ssh_user)
    await message.answer("SSH-пользователь:")


@router.message(AddServerStates.ssh_user)
async def add_server_ssh_user(message: Message, state: FSMContext) -> None:
    await state.update_data(ssh_user=(message.text or "").strip())
    await state.set_state(AddServerStates.ssh_port)
    await message.answer("SSH-порт (по умолчанию 22):")


@router.message(AddServerStates.ssh_port)
async def add_server_ssh_port(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not value:
        value = "22"
    await state.update_data(ssh_port=value)
    await state.set_state(AddServerStates.secret_type)
    await message.answer("Тип секрета (password/private_key/none):")


@router.message(AddServerStates.secret_type)
async def add_server_secret_type(message: Message, state: FSMContext) -> None:
    secret_type = (message.text or "").strip().lower()
    if secret_type not in SECRET_TYPE_MAP:
        await message.answer("Некорректный тип. Допустимо: password/private_key/none")
        return
    await state.update_data(secret_type=secret_type)
    if secret_type == "none":
        await state.update_data(secret_value=None)
        await state.set_state(AddServerStates.tags)
        await message.answer("Теги через запятую (или '-' если нет):")
        return

    await state.set_state(AddServerStates.secret_value)
    await message.answer("Введите значение секрета:")


@router.message(AddServerStates.secret_value)
async def add_server_secret_value(message: Message, state: FSMContext) -> None:
    await state.update_data(secret_value=(message.text or "").strip())
    await state.set_state(AddServerStates.tags)
    await message.answer("Теги через запятую (или '-' если нет):")


@router.message(AddServerStates.tags)
async def add_server_tags(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    tags = [] if raw == "-" else parse_tags_input(raw)
    await state.update_data(tags=tags)
    await state.set_state(AddServerStates.notes)
    await message.answer("Заметки (или '-' если нет):")


@router.message(AddServerStates.notes)
async def add_server_finish(message: Message, state: FSMContext, services: AppServices) -> None:
    if not message.from_user:
        await message.answer("Не удалось определить пользователя.")
        return
    user_id = message.from_user.id
    raw_notes = (message.text or "").strip()
    data = await state.get_data()
    try:
        schema = ServerCreateSchema(
            owner_telegram_id=user_id,
            name=data["name"],
            role=ROLE_MAP[data["role"]],
            provider=data["provider"],
            ip4=data["ip4"],
            ip6=data.get("ip6"),
            domain=data.get("domain"),
            ssh_port=int(data["ssh_port"]),
            ssh_user=data["ssh_user"],
            secret_type=SECRET_TYPE_MAP[data["secret_type"]],
            secret_value=data.get("secret_value"),
            tags=data.get("tags", []),
            notes="" if raw_notes == "-" else raw_notes,
        )
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"Ошибка валидации: {exc}")
        return

    try:
        server = await services.servers.create_server(schema)
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"Не удалось сохранить сервер: {exc}")
        return

    await state.clear()
    await message.answer(f"Сервер '{server.name}' добавлен.")

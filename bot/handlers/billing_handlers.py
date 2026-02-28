from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.dependencies import AppServices
from bot.keyboards.billing import billing_menu_keyboard, billing_server_select_keyboard
from bot.keyboards.main import CANCEL_MENU
from bot.states.billing_states import AddBillingStates
from bot.utils import parse_date_ru
from services.schemas import BillingCreateSchema

router = Router()


@router.callback_query(F.data == "bill:add_start")
async def bill_add_start(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    servers, _ = await services.servers.list_servers(user_id, page=1, page_size=100)
    if not servers:
        await query.answer("Сначала добавьте сервер", show_alert=True)
        return
    items = [(str(s.id), f"{s.name} ({s.ip4})") for s in servers]
    await query.message.answer("Выберите сервер:", reply_markup=billing_server_select_keyboard(items))
    await query.answer()


@router.callback_query(F.data.startswith("bill:expiring:"))
async def bill_expiring(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    days = int(query.data.split(":")[2])
    rows = await services.billing.list_expiring(user_id, days)
    if not rows:
        await query.message.edit_text(f"В ближайшие {days} дней истечений нет.", reply_markup=billing_menu_keyboard())
        await query.answer()
        return

    lines = [f"Истекают в {days} дней:"]
    for server, billing, delta in rows:
        lines.append(
            f"- {server.name} ({server.ip4}) -> {billing.expires_at.strftime('%d.%m.%Y')} ({delta} дн), {billing.price_amount} {billing.price_currency}"
        )
    await query.message.edit_text("\n".join(lines), reply_markup=billing_menu_keyboard())
    await query.answer()


@router.callback_query(F.data == "bill:summary")
async def bill_summary(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    summary = await services.billing.monthly_summary(user_id)
    if not summary:
        await query.message.answer("За текущий месяц оплат нет.")
        await query.answer()
        return
    lines = ["Сводка за текущий месяц:"]
    for currency, amount in summary.items():
        lines.append(f"- {amount} {currency}")
    await query.message.answer("\n".join(lines))
    await query.answer()


@router.callback_query(F.data.startswith("bill:add:"))
async def bill_add_for_server(query: CallbackQuery, state: FSMContext) -> None:
    server_id = query.data.split(":", maxsplit=2)[2]
    await state.clear()
    await state.update_data(server_id=server_id)
    await state.set_state(AddBillingStates.paid_at)
    await query.message.answer("Дата оплаты (ДД.ММ.ГГГГ):", reply_markup=CANCEL_MENU)
    await query.answer()


@router.message(F.text.casefold() == "отмена")
async def bill_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current and current.startswith(AddBillingStates.__name__):
        await state.clear()
        await message.answer("Добавление оплаты отменено.")


@router.message(AddBillingStates.paid_at)
async def bill_paid_at(message: Message, state: FSMContext) -> None:
    try:
        paid_at = parse_date_ru(message.text or "")
    except ValueError:
        await message.answer("Некорректная дата. Формат: ДД.ММ.ГГГГ")
        return
    await state.update_data(paid_at=paid_at)
    await state.set_state(AddBillingStates.expires_at)
    await message.answer("Дата истечения (ДД.ММ.ГГГГ):")


@router.message(AddBillingStates.expires_at)
async def bill_expires_at(message: Message, state: FSMContext) -> None:
    try:
        expires_at = parse_date_ru(message.text or "")
    except ValueError:
        await message.answer("Некорректная дата. Формат: ДД.ММ.ГГГГ")
        return
    await state.update_data(expires_at=expires_at)
    await state.set_state(AddBillingStates.amount)
    await message.answer("Сумма оплаты:")


@router.message(AddBillingStates.amount)
async def bill_amount(message: Message, state: FSMContext) -> None:
    await state.update_data(amount=(message.text or "").strip())
    await state.set_state(AddBillingStates.currency)
    await message.answer("Валюта (RUB/USD/EUR):")


@router.message(AddBillingStates.currency)
async def bill_currency(message: Message, state: FSMContext) -> None:
    await state.update_data(currency=(message.text or "").strip().upper())
    await state.set_state(AddBillingStates.period)
    await message.answer("Период (например 30d/1m/1y):")


@router.message(AddBillingStates.period)
async def bill_period(message: Message, state: FSMContext) -> None:
    await state.update_data(period=(message.text or "").strip())
    await state.set_state(AddBillingStates.comment)
    await message.answer("Комментарий (или '-' ):")


@router.message(AddBillingStates.comment)
async def bill_finish(message: Message, state: FSMContext, services: AppServices) -> None:
    data = await state.get_data()
    comment = (message.text or "").strip()
    if comment == "-":
        comment = None

    try:
        payload = BillingCreateSchema(
            server_id=data["server_id"],
            paid_at=data["paid_at"],
            expires_at=data["expires_at"],
            price_amount=data["amount"],
            price_currency=data["currency"],
            period=data["period"],
            comment=comment,
        )
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"Ошибка валидации: {exc}")
        return

    try:
        item = await services.billing.add_billing(payload)
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"Не удалось добавить оплату: {exc}")
        return

    await state.clear()
    await message.answer(
        f"Оплата добавлена. Истекает: {item.expires_at.strftime('%d.%m.%Y')}, {item.price_amount} {item.price_currency}",
        reply_markup=billing_menu_keyboard(),
    )


@router.callback_query(F.data.startswith("bill:list:"))
async def bill_list_server(query: CallbackQuery, services: AppServices, user_id: int) -> None:
    server_id = query.data.split(":", maxsplit=2)[2]
    rows = await services.billing.list_server_billings(user_id, server_id)
    if not rows:
        await query.answer("Оплат по серверу нет", show_alert=True)
        return
    lines = ["Все оплаты по серверу:"]
    for row in rows:
        lines.append(
            f"- {row.paid_at.strftime('%d.%m.%Y')} -> {row.expires_at.strftime('%d.%m.%Y')}, {row.price_amount} {row.price_currency} ({row.period})"
        )
    await query.message.answer("\n".join(lines))
    await query.answer()

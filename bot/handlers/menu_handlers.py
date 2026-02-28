from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from bot.keyboards.billing import billing_menu_keyboard
from bot.keyboards.main import MAIN_MENU
from bot.keyboards.manuals import manuals_menu_keyboard
from bot.keyboards.settings import settings_menu_keyboard
from bot.keyboards.vps import vps_menu_keyboard

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Flow Proxy Ops Vault\nВыберите раздел:",
        reply_markup=MAIN_MENU,
    )


@router.message(F.text == "📦 VPS")
async def open_vps(message: Message) -> None:
    await message.answer("VPS", reply_markup=vps_menu_keyboard())


@router.message(F.text == "📅 Оплаты / истечения")
async def open_billing(message: Message) -> None:
    await message.answer("Оплаты / истечения", reply_markup=billing_menu_keyboard())


@router.message(F.text == "📚 База знаний")
async def open_manuals(message: Message) -> None:
    await message.answer("📚 База знаний", reply_markup=manuals_menu_keyboard())


@router.message(F.text == "⚙️ Настройки")
async def open_settings(message: Message, is_admin: bool) -> None:
    if not is_admin:
        await message.answer("Раздел доступен только администратору.")
        return
    await message.answer("Настройки", reply_markup=settings_menu_keyboard())


@router.callback_query(F.data == "menu:vps")
async def cb_vps_menu(query: CallbackQuery) -> None:
    await query.message.edit_text("VPS", reply_markup=vps_menu_keyboard())
    await query.answer()


@router.callback_query(F.data == "menu:billing")
async def cb_billing_menu(query: CallbackQuery) -> None:
    await query.message.edit_text("Оплаты / истечения", reply_markup=billing_menu_keyboard())
    await query.answer()


@router.callback_query(F.data == "menu:manual")
async def cb_manual_menu(query: CallbackQuery) -> None:
    await query.message.edit_text("📚 База знаний", reply_markup=manuals_menu_keyboard())
    await query.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(query: CallbackQuery) -> None:
    await query.answer()

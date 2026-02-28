from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📦 VPS"), KeyboardButton(text="📅 Оплаты / истечения")],
        [KeyboardButton(text="🧠 Мануалы"), KeyboardButton(text="⚙️ Настройки")],
    ],
    resize_keyboard=True,
)

CANCEL_MENU = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Отмена")]],
    resize_keyboard=True,
    one_time_keyboard=True,
)

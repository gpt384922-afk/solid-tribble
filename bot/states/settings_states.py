from aiogram.fsm.state import State, StatesGroup


class WhitelistStates(StatesGroup):
    add_user = State()
    remove_user = State()


class SettingsStates(StatesGroup):
    set_secret_ttl = State()

from aiogram.fsm.state import State, StatesGroup


class AddServerStates(StatesGroup):
    name = State()
    provider = State()
    ip4 = State()
    domain = State()
    ssh_user = State()
    secret_type = State()
    secret_value = State()
    paid_at = State()
    expires_at = State()
    amount = State()
    confirm = State()


class SearchServerState(StatesGroup):
    query = State()

from aiogram.fsm.state import State, StatesGroup


class AddServerStates(StatesGroup):
    name = State()
    role = State()
    provider = State()
    ip4 = State()
    ip6 = State()
    domain = State()
    ssh_user = State()
    ssh_port = State()
    secret_type = State()
    secret_value = State()
    tags = State()
    notes = State()


class EditLoadStates(StatesGroup):
    notes = State()
    cpu = State()
    ram = State()
    disk = State()
    net_notes = State()


class SearchServerState(StatesGroup):
    query = State()

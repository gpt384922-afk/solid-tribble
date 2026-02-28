from aiogram.fsm.state import State, StatesGroup


class AddManualStates(StatesGroup):
    title = State()
    category = State()
    tags = State()
    body = State()


class SearchManualState(StatesGroup):
    query = State()


class EditManualStates(StatesGroup):
    title = State()
    category = State()
    tags = State()
    body = State()

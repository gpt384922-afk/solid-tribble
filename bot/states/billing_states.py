from aiogram.fsm.state import State, StatesGroup


class AddBillingStates(StatesGroup):
    server = State()
    paid_at = State()
    expires_at = State()
    amount = State()
    currency = State()
    period = State()
    comment = State()

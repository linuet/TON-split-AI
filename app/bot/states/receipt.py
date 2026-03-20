from aiogram.fsm.state import State, StatesGroup


class ReceiptStates(StatesGroup):
    waiting_for_receipt = State()
    waiting_for_participants = State()
    waiting_for_split_commands = State()

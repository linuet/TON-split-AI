from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.states.receipt import ReceiptStates

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ReceiptStates.waiting_for_receipt)
    await message.answer(
        "👋 Send me a clear photo of the receipt.\n\n"
        "After parsing, I will ask for participants and then you can assign items in plain language."
    )


@router.message(Command("new"))
async def cmd_new(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ReceiptStates.waiting_for_receipt)
    await message.answer("🆕 New split started. Send a receipt photo.")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Commands:\n"
        "/start — begin\n"
        "/new — start new receipt\n"
        "/cancel — cancel current flow\n\n"
        "Examples after parsing:\n"
        "me, Sasha, Dima\n"
        "coffee me\n"
        "pasta Sasha\n"
        "water split between me and Dima\n"
        "done"
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Cancelled. Send /start to begin again.")

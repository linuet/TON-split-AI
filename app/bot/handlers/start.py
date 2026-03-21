from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from app.bot.keyboards.common import restart_reply_kb
from app.bot.states.receipt import ReceiptStates

router = Router()


async def _go_to_waiting_receipt(message: Message, state: FSMContext, text: str) -> None:
    await state.clear()
    await state.set_state(ReceiptStates.waiting_for_receipt)
    await message.answer(text, reply_markup=restart_reply_kb())


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await _go_to_waiting_receipt(
        message,
        state,
        "👋 Send me a clear receipt photo.\n\n"
        "You can send a new photo at ANY moment — I will immediately start a fresh analysis.\n\n"
        "After parsing, I will ask for participants and then you can assign items in plain language.\n\n"
        "Examples:\n"
        "• coffee me\n"
        "• all drinks Misha\n"
        "• dessert split between me and Dima\n"
        "• everything else Anna\n"
        "• done",
    )


@router.message(Command("new"))
async def cmd_new(message: Message, state: FSMContext) -> None:
    await _go_to_waiting_receipt(message, state, "🆕 New split started. Send a receipt photo.")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Commands:\n"
        "/start — begin\n"
        "/new — start new receipt\n"
        "/cancel — cancel current flow\n\n"
        "At any moment you can:\n"
        "• send a new receipt photo — the bot will restart analysis automatically\n"
        "• tap \"🔄 Start over\" — the current flow will be reset\n\n"
        "After parsing:\n"
        "• send participants: <code>me, Sasha, Dima</code>\n"
        "• assign items: <code>coffee me</code>\n"
        "• use categories: <code>all drinks Misha</code>\n"
        "• group split: <code>dessert split between me and Dima</code>\n"
        "• fallback: <code>everything else me</code>\n"
        "• finalize: <code>done</code>",
        reply_markup=restart_reply_kb(),
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "❌ Cancelled. Send a new receipt photo when you're ready.",
        reply_markup=restart_reply_kb(),
    )


@router.message(F.text == "🔄 Start over")
async def start_over_text(message: Message, state: FSMContext) -> None:
    await _go_to_waiting_receipt(message, state, "🔄 Restarted. Send a new receipt photo.")


@router.callback_query(F.data == "split:restart")
async def start_over_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ReceiptStates.waiting_for_receipt)
    await callback.message.answer(
        "🔄 Restarted. Send a new receipt photo.",
        reply_markup=restart_reply_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "split:exit_view")
async def exit_receipt_view(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ReceiptStates.waiting_for_receipt)
    await callback.message.answer(
        "✖️ Receipt view closed. Send a new receipt photo when you want to continue.",
        reply_markup=restart_reply_kb(),
    )
    await callback.answer()

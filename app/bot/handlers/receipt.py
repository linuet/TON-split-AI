from pathlib import Path
from uuid import uuid4

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction, ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bot.keyboards.common import payment_kb, start_split_kb
from app.bot.states.receipt import ReceiptStates
from app.core.config import get_settings
from app.db.models import Receipt
from app.db.session import AsyncSessionLocal
from app.services.receipt.parser import ReceiptPipeline
from app.services.split.engine import SplitEngine
from app.utils.formatters import format_receipt, format_summary, format_payment_requests

router = Router()
settings = get_settings()
receipt_pipeline = ReceiptPipeline()
split_engine = SplitEngine()


@router.message(ReceiptStates.waiting_for_receipt, F.photo)
async def handle_receipt_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    photo = message.photo[-1]
    receipts_dir = settings.storage_dir / "receipts"
    original_path = receipts_dir / f"{uuid4().hex}.jpg"
    await bot.download(photo, destination=original_path)

    async with AsyncSessionLocal() as db:
        receipt = await receipt_pipeline.process(
            db=db,
            telegram_user_id=message.from_user.id,
            file_id=photo.file_id,
            original_path=Path(original_path),
        )

        split_session = await split_engine.create_session(db, receipt.id, message.from_user.id)
        await state.update_data(receipt_id=receipt.id, split_session_id=split_session.id)

    await state.set_state(ReceiptStates.waiting_for_participants)
    await message.answer(
        format_receipt(receipt) + "\n\nNow send participants separated by commas, for example:\n<code>me, Sasha, Dima</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=start_split_kb(),
    )


@router.callback_query(F.data == "split:add_participants")
async def ask_participants(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ReceiptStates.waiting_for_participants)
    await callback.message.answer("Send participants separated by commas. Example: <code>me, Sasha, Dima</code>")
    await callback.answer()


@router.callback_query(F.data == "split:equal")
async def split_equally(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    split_session_id = data.get("split_session_id")
    receipt_id = data.get("receipt_id")
    if not split_session_id or not receipt_id:
        await callback.answer("No active session", show_alert=True)
        return

    async with AsyncSessionLocal() as db:
        receipt = (
            await db.execute(select(Receipt).where(Receipt.id == receipt_id))
        ).scalar_one()
        session = await split_engine.get_session(db, split_session_id)
        if not session or not session.participants:
            await callback.answer("Add participants first", show_alert=True)
            return

        for item in receipt.items:
            command = f"{item.normalized_name} split between " + " and ".join([p.display_name for p in session.participants])
            await split_engine.apply_command(db, split_session_id, receipt, command)

        summary = await split_engine.build_summary(db, split_session_id, receipt)

    await state.set_state(ReceiptStates.waiting_for_split_commands)
    await callback.message.answer(
        format_summary(summary) + "\n\nSend more commands or type <code>done</code>.",
        parse_mode=ParseMode.HTML,
        reply_markup=payment_kb(),
    )
    await callback.answer()


@router.message(ReceiptStates.waiting_for_participants)
async def handle_participants(message: Message, state: FSMContext) -> None:
    names = [part.strip() for part in message.text.split(",") if part.strip()]
    if not names:
        await message.answer("Send at least one participant name separated by commas.")
        return

    data = await state.get_data()
    split_session_id = data["split_session_id"]
    async with AsyncSessionLocal() as db:
        participants = await split_engine.add_participants(db, split_session_id, names)

    await state.set_state(ReceiptStates.waiting_for_split_commands)
    await message.answer(
        "Participants added: " + ", ".join(p.display_name for p in participants) + "\n\n"
        "Now send split commands, for example:\n"
        "<code>coffee me</code>\n"
        "<code>pasta Sasha</code>\n"
        "<code>dessert split between me and Dima</code>\n"
        "<code>done</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=payment_kb(),
    )


@router.message(ReceiptStates.waiting_for_split_commands)
async def handle_split_commands(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    split_session_id = data["split_session_id"]
    receipt_id = data["receipt_id"]

    async with AsyncSessionLocal() as db:
        receipt = (
            await db.execute(select(Receipt).where(Receipt.id == receipt_id))
        ).scalar_one()
        summary, done = await split_engine.apply_command(db, split_session_id, receipt, message.text)

        if done:
            requests = await split_engine.create_payment_requests(db, split_session_id, receipt)
            await message.answer(
                format_summary(summary) + "\n\n" + format_payment_requests(requests),
                parse_mode=ParseMode.HTML,
            )
            await state.clear()
            return

    await message.answer(
        format_summary(summary) + "\n\nSend another command or type <code>done</code>.",
        parse_mode=ParseMode.HTML,
        reply_markup=payment_kb(),
    )


@router.callback_query(F.data == "split:payments")
async def create_payments(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    split_session_id = data.get("split_session_id")
    receipt_id = data.get("receipt_id")
    if not split_session_id or not receipt_id:
        await callback.answer("No active session", show_alert=True)
        return

    async with AsyncSessionLocal() as db:
        receipt = (
            await db.execute(select(Receipt).where(Receipt.id == receipt_id))
        ).scalar_one()
        requests = await split_engine.create_payment_requests(db, split_session_id, receipt)

    await callback.message.answer(format_payment_requests(requests), parse_mode=ParseMode.HTML)
    await callback.answer()

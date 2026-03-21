from pathlib import Path
from uuid import uuid4

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bot.keyboards.common import payment_kb, restart_reply_kb, start_split_kb
from app.bot.states.receipt import ReceiptStates
from app.core.config import get_settings
from app.db.models import Receipt
from app.db.session import AsyncSessionLocal
from app.services.ai.client import OpenAIService
from app.services.receipt.parser import ReceiptPipeline
from app.services.split.engine import SplitEngine
from app.utils.formatters import format_payment_requests, format_receipt, format_summary

router = Router()
settings = get_settings()
receipt_pipeline = ReceiptPipeline()
split_engine = SplitEngine()
ai_service = OpenAIService()


async def safe_edit_or_send(
    progress_message: Message,
    source_message: Message,
    text: str,
    *,
    parse_mode: ParseMode | str | None = None,
    reply_markup=None,
) -> Message:
    try:
        return await progress_message.edit_text(
            text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )
    except TelegramBadRequest:
        return await source_message.answer(
            text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )


@router.message(F.photo)
async def handle_receipt_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    # A photo should always start a completely fresh receipt flow.
    await state.clear()
    await state.set_state(ReceiptStates.waiting_for_receipt)

    progress_message = await message.answer(
        "🤖 AI is analyzing your receipt.\n"
        "This can take 20–30 seconds for a high-accuracy result.\n"
        "Please wait…",
        reply_markup=restart_reply_kb(),
    )

    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    photo = message.photo[-1]
    receipts_dir = settings.storage_dir / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)

    original_path = receipts_dir / f"{uuid4().hex}.jpg"
    await bot.download(photo, destination=original_path)

    try:
        async with AsyncSessionLocal() as db:
            receipt = await receipt_pipeline.process(
                db=db,
                telegram_user_id=message.from_user.id,
                file_id=photo.file_id,
                original_path=Path(original_path),
            )

            split_session = await split_engine.create_session(
                db,
                receipt.id,
                message.from_user.id,
            )

            await state.update_data(
                receipt_id=receipt.id,
                split_session_id=split_session.id,
            )

        await state.set_state(ReceiptStates.waiting_for_participants)

        await safe_edit_or_send(
            progress_message,
            message,
            format_receipt(receipt)
            + "\n\nNow send participants separated by commas, for example:\n"
              "<code>me, Sasha, Dima</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=start_split_kb(),
        )

    except Exception:
        await state.set_state(ReceiptStates.waiting_for_receipt)
        await safe_edit_or_send(
            progress_message,
            message,
            "⚠️ I couldn't finish analyzing this receipt.\n"
            "Send another, clearer photo or try again.\n"
            "You can also tap <b>🔄 Start over</b>.",
            parse_mode=ParseMode.HTML,
            reply_markup=restart_reply_kb(),
        )
        raise


@router.callback_query(F.data == "split:add_participants")
async def ask_participants(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ReceiptStates.waiting_for_participants)
    await callback.message.answer(
        "Send participants separated by commas.\n"
        "Example: <code>me, Sasha, Dima</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=restart_reply_kb(),
    )
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

        participant_names = [p.display_name for p in session.participants]
        command = "split all between " + " and ".join(participant_names)
        summary, _ = await split_engine.apply_command(
            db,
            split_session_id,
            receipt,
            command,
        )

    await state.set_state(ReceiptStates.waiting_for_split_commands)

    await callback.message.answer(
        format_summary(summary) + "\n\nSend more commands or type <code>done</code>.",
        parse_mode=ParseMode.HTML,
        reply_markup=payment_kb(),
    )
    await callback.answer()


@router.message(ReceiptStates.waiting_for_participants)
async def handle_participants(message: Message, state: FSMContext) -> None:
    parsed = await ai_service.parse_participants(message.text or "")
    names = parsed.participants
    if not names:
        await message.answer(
            "I couldn't confidently extract participant names. Try something like: <code>me, Sasha and Dima</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=restart_reply_kb(),
        )
        return

    data = await state.get_data()
    split_session_id = data["split_session_id"]

    async with AsyncSessionLocal() as db:
        participants = await split_engine.add_participants(db, split_session_id, names)

    await state.set_state(ReceiptStates.waiting_for_split_commands)

    await message.answer(
        "Participants added: "
        + ", ".join(p.display_name for p in participants)
        + "\n\nNow send split commands in plain language, for example:\n"
        + "<code>coffee me</code>\n"
        + "<code>all drinks me</code>\n"
        + "<code>dessert split between me and Dima</code>\n"
        + "<code>everything else Sasha</code>\n"
        + "<code>done</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=payment_kb(),
    )


@router.message(ReceiptStates.waiting_for_split_commands)
async def handle_split_commands(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    split_session_id = data["split_session_id"]
    receipt_id = data["receipt_id"]

    processing = await message.answer(
        "🧠 Thinking about the split…",
        reply_markup=restart_reply_kb(),
    )

    async with AsyncSessionLocal() as db:
        receipt = (
            await db.execute(select(Receipt).where(Receipt.id == receipt_id))
        ).scalar_one()

        summary, done = await split_engine.apply_command(
            db,
            split_session_id,
            receipt,
            message.text or "",
        )

        if done:
            if summary.unassigned_items:
                await safe_edit_or_send(
                    processing,
                    message,
                    format_summary(summary)
                    + "\n\nI still need those items assigned before I can create payment links.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=payment_kb(),
                )
                return

            requests = await split_engine.create_payment_requests(
                db,
                split_session_id,
                receipt,
            )

            await safe_edit_or_send(
                processing,
                message,
                format_summary(summary)
                + "\n\n✅ Split confirmed.\n\n"
                + format_payment_requests(requests),
                parse_mode=ParseMode.HTML,
                reply_markup=None,
            )

            await state.clear()
            await state.set_state(ReceiptStates.waiting_for_receipt)
            return

    critical_note = next((n for n in summary.notes if n.startswith("Critical clarification needed:")), None)
    hint = (
        critical_note
        if critical_note
        else (
            "Looks good. Type <code>done</code> to finalize or send corrections."
            if not summary.unassigned_items
            else "Send another command or type <code>done</code>."
        )
    )

    await safe_edit_or_send(
        processing,
        message,
        format_summary(summary) + f"\n\n{hint}",
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

        summary = await split_engine.build_summary(db, split_session_id, receipt)

        if summary.unassigned_items:
            await callback.message.answer(
                format_summary(summary)
                + "\n\nAssign the remaining items first, then create TON links.",
                parse_mode=ParseMode.HTML,
                reply_markup=payment_kb(),
            )
            await callback.answer()
            return

        requests = await split_engine.create_payment_requests(
            db,
            split_session_id,
            receipt,
        )

    await callback.message.answer(
        format_payment_requests(requests),
        parse_mode=ParseMode.HTML,
        reply_markup=restart_reply_kb(),
    )
    await callback.answer()
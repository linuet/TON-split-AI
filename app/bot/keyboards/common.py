from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def start_split_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Add participants", callback_data="split:add_participants")],
            [InlineKeyboardButton(text="➗ Split equally", callback_data="split:equal")],
            [InlineKeyboardButton(text="✖️ Exit receipt view", callback_data="split:exit_view")],
        ]
    )


def payment_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💎 Create TON links", callback_data="split:payments")],
            [InlineKeyboardButton(text="🔄 Start over", callback_data="split:restart")],
        ]
    )


def restart_reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔄 Start over")]],
        resize_keyboard=True,
        input_field_placeholder="Send a receipt photo or a split command…",
    )

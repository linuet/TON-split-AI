from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def start_split_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Add participants", callback_data="split:add_participants")],
            [InlineKeyboardButton(text="➗ Split equally", callback_data="split:equal")],
        ]
    )


def payment_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💎 Create TON links", callback_data="split:payments")]]
    )

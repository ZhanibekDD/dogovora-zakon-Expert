from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="flow:cancel")]]
    )

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def quick_draft_keyboard(contract_id: int) -> InlineKeyboardMarkup:
    """Keyboard for a quick-mode contract, which is generated already final (signature +
    stamp embedded, no separate approval step) - so there is no 'Утвердить' button here,
    only correction, redo, cancellation and sending it on to the client for signature."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Исправить", callback_data=f"quick:hint_edit:{contract_id}"),
                InlineKeyboardButton(text="🔄 Переделать условия", callback_data=f"quick:redo:{contract_id}"),
            ],
            [
                InlineKeyboardButton(
                    text="📤 Отправить клиенту на подписание",
                    callback_data=f"contract:send_signing:{contract_id}",
                )
            ],
            [InlineKeyboardButton(text="🗑 Отменить договор", callback_data=f"quick:delete:{contract_id}")],
        ]
    )

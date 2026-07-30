from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.keyboards.reply_menu import main_reply_keyboard
from app.database.models.user import User
from app.utils.telegram_text import escape_html

router = Router(name="start")

ROLE_LABELS = {
    "superadmin": "Супер-администратор",
    "admin": "Администратор",
    "manager": "Менеджер",
    "client": "Клиент",
}


@router.message(Command("start"))
async def cmd_start(message: Message, role: str | None, db_user: User) -> None:
    label = ROLE_LABELS.get(role or "", role or "")
    await message.answer(
        f"Здравствуйте, {escape_html(db_user.full_name)}!\n"
        f"Ваша роль: <b>{escape_html(label)}</b>\n\nВыберите действие в меню внизу экрана.",
        parse_mode="HTML",
        reply_markup=main_reply_keyboard(role or "", db_user.telegram_id),
    )

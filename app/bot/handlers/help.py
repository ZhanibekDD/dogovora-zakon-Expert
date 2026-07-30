from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.keyboards import reply_menu

router = Router(name="help")

HELP_TEXT = (
    "<b>Команды ZakonExpert Bot</b>\n\n"
    "/start — главное меню\n"
    "/new_contract — отправьте фото/PDF удостоверения с подписью, содержащей услугу, "
    "стоимость, оплату и телефон, — договор с подписью и печатью создастся сразу\n"
    "/contracts — список моих договоров\n"
    "/find_contract — найти договор по номеру или ФИО\n"
    "/templates — список утверждённых шаблонов\n"
    "/settings — настройки (для администраторов)\n"
    "/employees — управление сотрудниками (супер-администратор)\n"
    "/signature_settings — загрузка подписи и печати (супер-администратор)\n"
    "/backup — резервное копирование (супер-администратор)\n"
    "/help — эта справка\n\n"
    "💡 Команда /new_contract не обязательна: если вы просто отправите фото/PDF "
    "удостоверения с подписью, где явно упомянута услуга или сумма, бот распознает это "
    "как запрос на новый договор автоматически.\n\n"
    "💡 Чтобы исправить уже готовый договор, ответьте (reply) на сообщение с ним обычным "
    'текстом, например: "Поменяй стоимость на 30000".'
)


@router.message(Command("help"))
@router.message(F.text == reply_menu.HELP)
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML")

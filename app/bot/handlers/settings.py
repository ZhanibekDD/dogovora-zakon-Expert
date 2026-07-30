from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from app.bot.keyboards import reply_menu
from app.bot.states.contract_states import SettingsStates
from app.core.config import get_settings
from app.database.models.contract import ContractCounter
from app.database.models.user import User
from app.database.repositories.counter_repo import set_next_contract_number
from app.database.session import session_scope
from app.services.audit_service import log_action

router = Router(name="settings")

SUPERADMIN_ONLY = {"superadmin"}


def _settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔢 Изменить следующий номер договора", callback_data="settings:set_number")],
        ]
    )


@router.message(Command("settings"))
@router.message(F.text == reply_menu.SETTINGS)
async def show_settings(message: Message, role: str | None) -> None:
    if role not in ("admin", "superadmin"):
        await message.answer("⛔ Доступно только администраторам.")
        return

    settings = get_settings()
    async with session_scope() as session:
        result = await session.execute(select(ContractCounter).where(ContractCounter.id == 1))
        counter = result.scalar_one_or_none()
        next_number = (counter.current_number + 1) if counter else settings.contract_number_start

    text = (
        "<b>Реквизиты Исполнителя</b>\n"
        f"{settings.executor_full_name}\n"
        f"Коммерческое обозначение: {settings.executor_brand_name}\n"
        f"ИИН: {settings.executor_iin}\n"
        f"Адрес: {settings.executor_address}\n"
        f"Телефон/WhatsApp: {settings.executor_phone}\n"
        f"Kaspi: {settings.executor_kaspi_number} ({settings.executor_kaspi_receiver})\n\n"
        f"Следующий номер договора: <b>{next_number}</b>\n\n"
        "Изменение реквизитов ИП выполняется через переменные окружения (.env) супер-"
        "администратором и требует перезапуска бота."
    )
    keyboard = _settings_keyboard() if role == "superadmin" else None
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data == "settings:set_number")
async def ask_next_number(callback: CallbackQuery, role: str | None, state: FSMContext) -> None:
    if role not in SUPERADMIN_ONLY:
        await callback.answer("⛔ Доступно только супер-администратору.", show_alert=True)
        return
    await state.set_state(SettingsStates.waiting_for_next_contract_number)
    await callback.message.answer("Введите новый следующий номер договора (целое число):")
    await callback.answer()


@router.message(SettingsStates.waiting_for_next_contract_number)
async def receive_next_number(message: Message, state: FSMContext) -> None:
    if not message.text.strip().isdigit():
        await message.answer("⛔ Введите целое положительное число.")
        return
    await state.update_data(next_number=int(message.text.strip()))
    await state.set_state(SettingsStates.waiting_for_next_contract_number_reason)
    await message.answer("Укажите причину изменения нумерации (обязательно для журнала):")


@router.message(SettingsStates.waiting_for_next_contract_number_reason)
async def receive_next_number_reason(message: Message, state: FSMContext, db_user: User) -> None:
    data = await state.get_data()
    next_number = data["next_number"]
    reason = message.text.strip()

    async with session_scope() as session:
        await set_next_contract_number(session, next_number, reason, changed_by_user_id=db_user.id)
        await log_action(
            session,
            action="contract_counter_changed",
            user_id=db_user.id,
            telegram_id=db_user.telegram_id,
            details={"next_number": next_number, "reason": reason},
        )
    await state.clear()
    await message.answer(f"✅ Следующий номер договора установлен: {next_number}")

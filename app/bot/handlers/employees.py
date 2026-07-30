from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from app.database.models.user import Employee, User
from app.database.repositories.user_repo import get_role_by_code
from app.database.session import session_scope
from app.services.audit_service import log_action
from app.utils.telegram_text import escape_html

router = Router(name="employees")


def _role_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Менеджер", callback_data="employee_role:manager")],
            [InlineKeyboardButton(text="Администратор", callback_data="employee_role:admin")],
        ]
    )


@router.message(Command("employees"))
async def employees_menu(message: Message, role: str | None) -> None:
    if role != "superadmin":
        await message.answer("⛔ Доступно только супер-администратору.")
        return

    async with session_scope() as session:
        result = await session.execute(
            select(User, Employee)
            .join(Employee, Employee.user_id == User.id)
            .order_by(User.id)
        )
        rows = result.all()

    lines = ["<b>Сотрудники:</b>"]
    for user, employee in rows:
        status = "🚫 заблокирован" if employee.is_blocked else "✅ активен"
        lines.append(
            f"{escape_html(user.full_name)} (ID {user.telegram_id}) — {user.role.code} — {status}"
        )
    lines.append(
        "\nЧтобы добавить сотрудника, отправьте: /employees_add &lt;telegram_id&gt; &lt;ФИО&gt;"
    )
    lines.append("Чтобы заблокировать: /employees_block &lt;telegram_id&gt;")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("employees_add"))
async def add_employee(message: Message, role: str | None, db_user: User) -> None:
    if role != "superadmin":
        await message.answer("⛔ Доступно только супер-администратору.")
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit():
        await message.answer("Использование: /employees_add <telegram_id> <ФИО>")
        return

    telegram_id = int(parts[1])
    full_name = parts[2]

    async with session_scope() as session:
        manager_role = await get_role_by_code(session, "manager")
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(telegram_id=telegram_id, full_name=full_name, role_id=manager_role.id, is_active=True)
            session.add(user)
            await session.flush()
        session.add(Employee(user_id=user.id, added_by_user_id=db_user.id))
        await log_action(
            session,
            action="employee_added",
            user_id=db_user.id,
            telegram_id=db_user.telegram_id,
            entity_type="user",
            entity_id=user.id,
            details={"new_employee_telegram_id": telegram_id},
        )

    await message.answer(f"✅ Сотрудник {full_name} (ID {telegram_id}) добавлен с ролью «менеджер».")


@router.message(Command("employees_block"))
async def block_employee(message: Message, role: str | None, db_user: User) -> None:
    if role != "superadmin":
        await message.answer("⛔ Доступно только супер-администратору.")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer("Использование: /employees_block <telegram_id>")
        return

    telegram_id = int(parts[1].strip())
    async with session_scope() as session:
        result = await session.execute(
            select(User, Employee).join(Employee, Employee.user_id == User.id).where(User.telegram_id == telegram_id)
        )
        row = result.first()
        if row is None:
            await message.answer("Сотрудник не найден.")
            return
        user, employee = row
        employee.is_blocked = True
        employee.blocked_reason = "Заблокирован супер-администратором"
        await log_action(
            session,
            action="employee_blocked",
            user_id=db_user.id,
            telegram_id=db_user.telegram_id,
            entity_type="user",
            entity_id=user.id,
        )

    await message.answer(f"🚫 Сотрудник ID {telegram_id} заблокирован.")

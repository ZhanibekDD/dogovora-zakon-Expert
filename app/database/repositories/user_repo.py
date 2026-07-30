from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.user import Employee, Role, User


async def get_role_by_code(session: AsyncSession, code: str) -> Role | None:
    result = await session.execute(select(Role).where(Role.code == code))
    return result.scalar_one_or_none()


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def get_active_employee_by_telegram_id(
    session: AsyncSession, telegram_id: int
) -> User | None:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None or not user.is_active:
        return None
    if user.role.code == "client":
        return user
    result = await session.execute(select(Employee).where(Employee.user_id == user.id))
    employee = result.scalar_one_or_none()
    if employee is not None and employee.is_blocked:
        return None
    return user

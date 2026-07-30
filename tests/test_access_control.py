from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.user import Employee, User
from app.database.repositories.user_repo import get_active_employee_by_telegram_id, get_role_by_code


async def test_unknown_telegram_id_has_no_access(db_session: AsyncSession) -> None:
    user = await get_active_employee_by_telegram_id(db_session, telegram_id=999999999)
    assert user is None


async def test_known_active_manager_has_access(db_session: AsyncSession) -> None:
    role = await get_role_by_code(db_session, "manager")
    user = User(telegram_id=123456, full_name="Manager One", role_id=role.id, is_active=True)
    db_session.add(user)
    await db_session.flush()
    db_session.add(Employee(user_id=user.id))
    await db_session.flush()

    resolved = await get_active_employee_by_telegram_id(db_session, telegram_id=123456)
    assert resolved is not None
    assert resolved.telegram_id == 123456


async def test_blocked_employee_denied_access(db_session: AsyncSession) -> None:
    role = await get_role_by_code(db_session, "manager")
    user = User(telegram_id=777888, full_name="Blocked Manager", role_id=role.id, is_active=True)
    db_session.add(user)
    await db_session.flush()
    db_session.add(Employee(user_id=user.id, is_blocked=True, blocked_reason="test"))
    await db_session.flush()

    resolved = await get_active_employee_by_telegram_id(db_session, telegram_id=777888)
    assert resolved is None


async def test_inactive_user_denied_access(db_session: AsyncSession) -> None:
    role = await get_role_by_code(db_session, "manager")
    user = User(telegram_id=321321, full_name="Inactive", role_id=role.id, is_active=False)
    db_session.add(user)
    await db_session.flush()

    resolved = await get_active_employee_by_telegram_id(db_session, telegram_id=321321)
    assert resolved is None

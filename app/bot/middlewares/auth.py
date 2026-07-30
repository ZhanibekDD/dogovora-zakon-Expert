from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy import select

from app.core.logging import get_logger
from app.database.models.user import Employee, User
from app.database.repositories.user_repo import get_role_by_code
from app.database.session import session_scope

logger = get_logger(__name__)

DEFAULT_AUTO_PROVISION_ROLE = "manager"


class AuthMiddleware(BaseMiddleware):
    """Resolves the Telegram user against the employees table on every update.

    Open-access mode: anyone who messages the bot for the first time is auto-provisioned as
    a `manager` (the lowest-privilege staff role) instead of being rejected, per an explicit
    decision to open the bot to everyone. Accounts that already exist and were explicitly
    blocked (or deactivated) via /employees_block are still refused - blocking remains
    possible, it just no longer defaults to "deny everyone not pre-approved".
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        telegram_id: int | None = None
        full_name = "Telegram User"
        username: str | None = None
        if isinstance(event, Message) and event.from_user or isinstance(event, CallbackQuery) and event.from_user:
            telegram_id = event.from_user.id
            full_name = event.from_user.full_name
            username = event.from_user.username

        if telegram_id is None:
            return await handler(event, data)

        async with session_scope() as session:
            result = await session.execute(select(User).where(User.telegram_id == telegram_id))
            user = result.scalar_one_or_none()

            if user is None:
                manager_role = await get_role_by_code(session, DEFAULT_AUTO_PROVISION_ROLE)
                user = User(
                    telegram_id=telegram_id,
                    username=username,
                    full_name=full_name,
                    role_id=manager_role.id,
                    is_active=True,
                )
                session.add(user)
                await session.flush()
                session.add(Employee(user_id=user.id))
                await session.flush()
                role_code = manager_role.code
                logger.info("user_auto_provisioned", telegram_id=telegram_id)
            else:
                employee_result = await session.execute(
                    select(Employee).where(Employee.user_id == user.id)
                )
                employee = employee_result.scalar_one_or_none()
                if not user.is_active or (employee is not None and employee.is_blocked):
                    if isinstance(event, Message):
                        await event.answer(
                            "⛔ Ваш доступ к этому боту заблокирован администратором ZakonExpert."
                        )
                    elif isinstance(event, CallbackQuery):
                        await event.answer("⛔ Доступ заблокирован", show_alert=True)
                    logger.warning("blocked_user_access_attempt", telegram_id=telegram_id)
                    return None
                role_code = user.role.code

            data["db_user"] = user
            data["role"] = role_code

        return await handler(event, data)

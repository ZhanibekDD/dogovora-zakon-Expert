from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.models.user import Employee, User
from app.database.repositories.user_repo import get_role_by_code
from app.database.session import session_scope

logger = get_logger(__name__)

DEFAULT_PROVISION_ROLE = "manager"
SUPERADMIN_ROLE = "superadmin"

UNAUTHORIZED_MESSAGE = (
    "⛔ Этот бот доступен только сотрудникам ZakonExpert.\n"
    "Ваш Telegram ID: {telegram_id}"
)


class AuthMiddleware(BaseMiddleware):
    """Lets only allowlisted Telegram IDs use the bot.

    Closed-access mode: the allowlist is SUPERADMIN_TELEGRAM_IDS plus BOT_ALLOWED_TELEGRAM_IDS
    (see Settings.bot_access_ids). Everyone else is refused before any database access,
    including users that were auto-provisioned earlier under the old open-access mode.
    An empty allowlist refuses everyone (fail closed).

    Allowlisted IDs missing from the database are created on first contact: superadmin IDs
    with the superadmin role, the rest as managers. Accounts blocked or deactivated via
    /employees_block stay refused even when allowlisted.
    """

    def __init__(self, allowed_ids: Iterable[int] | None = None) -> None:
        self._allowed_ids = frozenset(allowed_ids) if allowed_ids is not None else None

    def _allowed(self) -> frozenset[int]:
        if self._allowed_ids is not None:
            return self._allowed_ids
        return frozenset(get_settings().bot_access_ids)

    @staticmethod
    def _superadmin_ids() -> set[int]:
        return get_settings().superadmin_ids

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

        if telegram_id not in self._allowed():
            if isinstance(event, Message):
                await event.answer(UNAUTHORIZED_MESSAGE.format(telegram_id=telegram_id))
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔ Нет доступа", show_alert=True)
            logger.warning("unauthorized_access_attempt", telegram_id=telegram_id)
            return None

        async with session_scope() as session:
            result = await session.execute(select(User).where(User.telegram_id == telegram_id))
            user = result.scalar_one_or_none()

            if user is None:
                role_code = (
                    SUPERADMIN_ROLE if telegram_id in self._superadmin_ids() else DEFAULT_PROVISION_ROLE
                )
                role = await get_role_by_code(session, role_code)
                user = User(
                    telegram_id=telegram_id,
                    username=username,
                    full_name=full_name,
                    role_id=role.id,
                    is_active=True,
                )
                session.add(user)
                await session.flush()
                session.add(Employee(user_id=user.id))
                await session.flush()
                role_code = role.code
                logger.info("allowlisted_user_provisioned", telegram_id=telegram_id, role=role_code)
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

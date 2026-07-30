from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.database.session import session_scope
from app.services.audit_service import log_action


class AuditMiddleware(BaseMiddleware):
    """Lightweight trail of every command/callback an authenticated user triggers."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        db_user = data.get("db_user")
        if db_user is not None:
            action = None
            if isinstance(event, Message) and event.text:
                action = f"message:{event.text.split()[0]}"
            elif isinstance(event, CallbackQuery) and event.data:
                action = f"callback:{event.data}"
            if action:
                async with session_scope() as session:
                    await log_action(
                        session, action=action, user_id=db_user.id, telegram_id=db_user.telegram_id
                    )
        return await handler(event, data)

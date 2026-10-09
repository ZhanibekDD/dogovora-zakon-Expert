from __future__ import annotations

import datetime
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from aiogram.types import CallbackQuery, Chat, Message
from aiogram.types import User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.middlewares import auth as auth_module
from app.bot.middlewares.auth import AuthMiddleware
from app.core.config import Settings
from app.database.models.user import Employee, User
from app.database.repositories.user_repo import get_role_by_code

OWNER_ID = 111111111  # matches SUPERADMIN_TELEGRAM_IDS set in conftest
STRANGER_ID = 555000555


def _tg_user(telegram_id: int) -> TgUser:
    return TgUser.model_construct(id=telegram_id, is_bot=False, first_name="Test", last_name=None, username=None)


def _message(telegram_id: int, answers: list[str]) -> Message:
    class _Message(Message):
        async def answer(self, text: str, **kwargs: Any) -> None:  # type: ignore[override]
            answers.append(text)

    return _Message.model_construct(
        message_id=1,
        date=datetime.datetime.now(datetime.UTC),
        chat=Chat.model_construct(id=telegram_id, type="private"),
        from_user=_tg_user(telegram_id),
        text="/start",
    )


def _callback(telegram_id: int, answers: list[str]) -> CallbackQuery:
    class _Callback(CallbackQuery):
        async def answer(self, text: str | None = None, **kwargs: Any) -> None:  # type: ignore[override]
            answers.append(text or "")

    return _Callback.model_construct(
        id="cb-1", from_user=_tg_user(telegram_id), chat_instance="ci", data="quick:redo:1"
    )


class _Handler:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, event: Any, data: dict[str, Any]) -> str:
        self.calls.append(dict(data))
        return "handled"


@pytest.fixture
def use_test_session(monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession) -> AsyncSession:
    @asynccontextmanager
    async def _scope() -> AsyncIterator[AsyncSession]:
        yield db_session
        await db_session.flush()

    monkeypatch.setattr(auth_module, "session_scope", _scope)
    return db_session


@pytest.fixture
def no_database(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def _forbidden() -> AsyncIterator[AsyncSession]:
        raise AssertionError("strangers must be refused before any database access")
        yield  # pragma: no cover

    monkeypatch.setattr(auth_module, "session_scope", _forbidden)


async def test_stranger_message_is_refused_without_touching_database(no_database: None) -> None:
    answers: list[str] = []
    handler = _Handler()

    result = await AuthMiddleware(allowed_ids={OWNER_ID})(handler, _message(STRANGER_ID, answers), {})

    assert result is None
    assert handler.calls == []
    assert len(answers) == 1
    assert str(STRANGER_ID) in answers[0]


async def test_stranger_callback_is_refused(no_database: None) -> None:
    answers: list[str] = []
    handler = _Handler()

    result = await AuthMiddleware(allowed_ids={OWNER_ID})(handler, _callback(STRANGER_ID, answers), {})

    assert result is None
    assert handler.calls == []
    assert answers == ["⛔ Нет доступа"]


async def test_empty_allowlist_refuses_everyone(no_database: None) -> None:
    answers: list[str] = []
    handler = _Handler()

    result = await AuthMiddleware(allowed_ids=set())(handler, _message(OWNER_ID, answers), {})

    assert result is None
    assert handler.calls == []


async def test_previously_auto_provisioned_manager_is_now_refused(
    use_test_session: AsyncSession,
) -> None:
    role = await get_role_by_code(use_test_session, "manager")
    user = User(telegram_id=STRANGER_ID, full_name="Old Open Access User", role_id=role.id, is_active=True)
    use_test_session.add(user)
    await use_test_session.flush()
    use_test_session.add(Employee(user_id=user.id))
    await use_test_session.flush()

    answers: list[str] = []
    handler = _Handler()
    result = await AuthMiddleware(allowed_ids={OWNER_ID})(handler, _message(STRANGER_ID, answers), {})

    assert result is None
    assert handler.calls == []


async def test_owner_unknown_to_database_is_provisioned_as_superadmin(
    use_test_session: AsyncSession,
) -> None:
    answers: list[str] = []
    handler = _Handler()

    result = await AuthMiddleware(allowed_ids={OWNER_ID})(handler, _message(OWNER_ID, answers), {})

    assert result == "handled"
    assert answers == []
    assert handler.calls[0]["role"] == "superadmin"
    stored = (await use_test_session.execute(select(User).where(User.telegram_id == OWNER_ID))).scalar_one()
    assert stored.is_active


async def test_allowlisted_employee_unknown_to_database_is_provisioned_as_manager(
    use_test_session: AsyncSession,
) -> None:
    employee_id = 222333444
    handler = _Handler()

    result = await AuthMiddleware(allowed_ids={OWNER_ID, employee_id})(handler, _message(employee_id, []), {})

    assert result == "handled"
    assert handler.calls[0]["role"] == "manager"


async def test_blocked_allowlisted_employee_is_still_refused(use_test_session: AsyncSession) -> None:
    employee_id = 222333444
    role = await get_role_by_code(use_test_session, "manager")
    user = User(telegram_id=employee_id, full_name="Blocked", role_id=role.id, is_active=True)
    use_test_session.add(user)
    await use_test_session.flush()
    use_test_session.add(Employee(user_id=user.id, is_blocked=True, blocked_reason="test"))
    await use_test_session.flush()

    answers: list[str] = []
    handler = _Handler()
    result = await AuthMiddleware(allowed_ids={OWNER_ID, employee_id})(handler, _message(employee_id, answers), {})

    assert result is None
    assert handler.calls == []
    assert "заблокирован" in answers[0]


def test_bot_access_ids_combines_superadmins_and_allowlist() -> None:
    settings = Settings(
        SUPERADMIN_TELEGRAM_IDS="1192625794",
        BOT_ALLOWED_TELEGRAM_IDS=" 42, 43 ",
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        DATABASE_URL_SYNC="sqlite:///:memory:",
        APP_SECRET_KEY="x",
        TELEGRAM_BOT_TOKEN="t",
    )
    assert settings.bot_access_ids == {1192625794, 42, 43}


def test_bot_access_ids_defaults_to_superadmins_only() -> None:
    settings = Settings(
        SUPERADMIN_TELEGRAM_IDS="1192625794",
        BOT_ALLOWED_TELEGRAM_IDS="",
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        DATABASE_URL_SYNC="sqlite:///:memory:",
        APP_SECRET_KEY="x",
        TELEGRAM_BOT_TOKEN="t",
    )
    assert settings.bot_access_ids == {1192625794}

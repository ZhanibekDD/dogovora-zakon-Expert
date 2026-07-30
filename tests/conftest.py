from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

_TMP_STORAGE = tempfile.mkdtemp(prefix="zakonexpert_test_storage_")

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key")
os.environ.setdefault("SUPERADMIN_TELEGRAM_IDS", "111111111")
os.environ.setdefault("STORAGE_PATH", _TMP_STORAGE)
os.environ.setdefault("BACKUP_ENCRYPTION_KEY", "wDGl2Qk3vN8x0F8m3s1yq5S3f9F3vQzX3v8b1n0m2Zc=")

from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database.base import Base  # noqa: E402
from app.database.models.user import Role  # noqa: E402


def pytest_sessionfinish(session, exitstatus) -> None:
    shutil.rmtree(_TMP_STORAGE, ignore_errors=True)


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        for code, name in [
            ("superadmin", "Супер-администратор"),
            ("admin", "Администратор"),
            ("manager", "Менеджер"),
            ("client", "Клиент"),
        ]:
            session.add(Role(code=code, name=name))
        await session.commit()
        yield session

    await engine.dispose()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"

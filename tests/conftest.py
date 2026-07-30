from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import AsyncIterator
from contextlib import suppress

import pytest
import pytest_asyncio
from PIL import Image, ImageDraw

_TMP_STORAGE = tempfile.mkdtemp(prefix="zakonexpert_test_storage_")
_CREATED_TEST_ASSETS: list[str] = []

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key")
os.environ.setdefault("SUPERADMIN_TELEGRAM_IDS", "111111111")
os.environ.setdefault("STORAGE_PATH", _TMP_STORAGE)
os.environ.setdefault("BACKUP_ENCRYPTION_KEY", "wDGl2Qk3vN8x0F8m3s1yq5S3f9F3vQzX3v8b1n0m2Zc=")


def _ensure_test_executor_assets() -> None:
    """Create harmless ignored fixtures only when real local assets are absent."""

    asset_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "app",
        "templates",
        "assets",
        "signature",
    )
    os.makedirs(asset_dir, exist_ok=True)
    created_kinds: set[str] = set()
    for kind in ("signature", "stamp"):
        path = os.path.join(asset_dir, f"executor_{kind}.png")
        if os.path.exists(path):
            continue
        image = Image.new("RGBA", (600, 220 if kind == "signature" else 600), (255, 255, 255, 0))
        draw = ImageDraw.Draw(image)
        if kind == "signature":
            draw.line((70, 145, 520, 70), fill=(25, 76, 160, 255), width=14)
            draw.arc((110, 50, 470, 190), 180, 350, fill=(25, 76, 160, 255), width=10)
        else:
            draw.ellipse((35, 35, 565, 565), outline=(25, 76, 160, 255), width=18)
            draw.ellipse((80, 80, 520, 520), outline=(25, 76, 160, 255), width=7)
        image.save(path, format="PNG")
        _CREATED_TEST_ASSETS.append(path)
        created_kinds.add(kind)

    # Bind only the disposable pair created by this test session. Never modify a developer's
    # real local assets or their manifest.
    if created_kinds == {"signature", "stamp"}:
        manifest_path = os.path.join(asset_dir, "hashes.json")
        assets = {}
        for kind in created_kinds:
            path = os.path.join(asset_dir, f"executor_{kind}.png")
            with open(path, "rb") as stream:
                assets[kind] = hashlib.sha256(stream.read()).hexdigest()
        with open(manifest_path, "w", encoding="utf-8") as stream:
            json.dump(
                {
                    "version": 1,
                    "legal_identity": "БИН:260740044168",
                    "identifier_label": "БИН",
                    "identifier": "260740044168",
                    "assets": assets,
                },
                stream,
                ensure_ascii=False,
                indent=2,
            )
        _CREATED_TEST_ASSETS.append(manifest_path)


_ensure_test_executor_assets()

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
    for path in _CREATED_TEST_ASSETS:
        with suppress(FileNotFoundError):
            os.remove(path)


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    # Each test gets a fresh database with IDs starting at 1; mirror that isolation on disk
    # so a previous test's final_v1.pdf cannot collide with the next test's contract ID 1.
    shutil.rmtree(os.path.join(_TMP_STORAGE, "documents"), ignore_errors=True)
    os.makedirs(os.path.join(_TMP_STORAGE, "documents"), exist_ok=True)
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

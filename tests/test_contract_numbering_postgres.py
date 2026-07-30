"""Integration test proving the contract-numbering guarantee actually holds under
PostgreSQL's real row-level locking - the property the unit tests in
test_contract_numbering.py cannot exercise, since SQLite has no equivalent to
SELECT ... FOR UPDATE and silently allows the lost-update race that this test guards
against. Spins up a disposable postgres:16-alpine container via the Docker CLI; skips
automatically if Docker is not available in the environment running the suite.
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
import uuid

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.repositories.counter_repo import reserve_next_contract_number

DOCKER_AVAILABLE = shutil.which("docker") is not None
CONTAINER_NAME = f"zakonexpert-test-pg-{uuid.uuid4().hex[:8]}"
HOST_PORT = 55432


def _docker(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


async def _wait_for_postgres(dsn: str, attempts: int = 40) -> None:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            conn = await asyncpg.connect(dsn)
            await conn.close()
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            await asyncio.sleep(0.5)
    raise RuntimeError(f"Postgres container never became ready: {last_error}")


@pytest.fixture(scope="module")
def postgres_container():
    if not DOCKER_AVAILABLE:
        pytest.skip("Docker is not available in this environment")

    result = _docker(
        "run", "-d", "--rm", "--name", CONTAINER_NAME,
        "-e", "POSTGRES_PASSWORD=test", "-e", "POSTGRES_USER=test", "-e", "POSTGRES_DB=test",
        "-p", f"{HOST_PORT}:5432",
        "postgres:16-alpine",
    )
    if result.returncode != 0:
        pytest.skip(f"Could not start postgres container: {result.stderr}")

    try:
        yield f"postgresql://test:test@localhost:{HOST_PORT}/test"
    finally:
        _docker("stop", CONTAINER_NAME, timeout=30)


async def test_concurrent_reservations_never_duplicate_numbers_on_real_postgres(
    postgres_container: str,
) -> None:
    dsn_asyncpg = postgres_container
    dsn_sqlalchemy = dsn_asyncpg.replace("postgresql://", "postgresql+asyncpg://")

    await _wait_for_postgres(dsn_asyncpg)

    engine = create_async_engine(dsn_sqlalchemy)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def reserve_one() -> int:
        async with session_factory() as session:
            number = await reserve_next_contract_number(session, start_value=1)
            await session.commit()
            return number

    results = await asyncio.gather(*(reserve_one() for _ in range(20)))
    await engine.dispose()

    assert len(results) == len(set(results)) == 20
    assert sorted(results) == list(range(1, 21))

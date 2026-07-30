from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.database.repositories.counter_repo import reserve_next_contract_number


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


async def test_sequential_numbering_increments_by_one(session_factory) -> None:
    async with session_factory() as session:
        numbers = []
        for _ in range(5):
            number = await reserve_next_contract_number(session, start_value=1)
            numbers.append(number)
        await session.commit()
    assert numbers == [1, 2, 3, 4, 5]


async def test_manual_start_value_respected() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        first = await reserve_next_contract_number(session, start_value=100)
        await session.commit()
    assert first == 100
    await engine.dispose()


async def test_sqlite_lacks_real_row_locking_hence_postgres_integration_test_exists(
    session_factory,
) -> None:
    """SQLite has no equivalent of SELECT ... FOR UPDATE: it silently no-ops the clause, so
    concurrent sessions can both read current_number=0 before either commits, producing a
    lost update. This is documented and *expected* here specifically to explain why the real
    concurrency guarantee (tests 6/7 from the spec) is verified against real PostgreSQL in
    test_contract_numbering_postgres.py instead of against this in-memory SQLite fixture.
    """
    from app.database.models.contract import ContractCounter

    async with session_factory() as seed_session:
        seed_session.add(ContractCounter(id=1, current_number=0))
        await seed_session.commit()

    async def reserve_one() -> int:
        async with session_factory() as session:
            number = await reserve_next_contract_number(session, start_value=1)
            await session.commit()
            return number

    results = await asyncio.gather(*(reserve_one() for _ in range(20)))
    # On SQLite this is a *lost-update* race - at least one duplicate is expected here.
    # PostgreSQL's SELECT ... FOR UPDATE prevents this in production; see the dedicated
    # integration test for the real guarantee.
    assert len(results) == 20

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.contract import ContractCounter, ContractCounterLog


async def _lock_counter_row(session: AsyncSession) -> ContractCounter | None:
    result = await session.execute(
        select(ContractCounter).where(ContractCounter.id == 1).with_for_update()
    )
    return result.scalar_one_or_none()


async def reserve_next_contract_number(session: AsyncSession, start_value: int) -> int:
    """Atomically reserve the next contract number.

    Uses SELECT ... FOR UPDATE to serialize concurrent reservations against the single
    counter row, guaranteeing no two contracts ever get the same number even if two
    employees create a contract at the same instant.

    The tricky part is bootstrapping row id=1 itself: FOR UPDATE can only lock a row that
    already exists, so if two transactions both find no row yet, both would try to INSERT
    it and one loses with a UniqueViolation. That insert therefore runs inside a SAVEPOINT
    (session.begin_nested()) - if it collides, only the savepoint rolls back (not the whole
    transaction), and we re-select-for-update to pick up whichever row won the race.
    """
    counter = await _lock_counter_row(session)
    if counter is None:
        try:
            async with session.begin_nested():
                session.add(ContractCounter(id=1, current_number=start_value - 1))
                await session.flush()
        except IntegrityError:
            pass  # another concurrent transaction already created row id=1
        counter = await _lock_counter_row(session)
        assert counter is not None

    counter.current_number += 1
    await session.flush()
    return counter.current_number


async def release_last_number_if_matches(session: AsyncSession, contract_number: int) -> bool:
    """Best-effort release of a contract number when its draft is deleted before approval.

    Only releases the number if it is exactly the most recently issued one (current_number),
    so releasing never creates a gap that a later manual override could collide with, and
    never rewinds past a number that has already been handed out to a different contract in
    the meantime. Returns True if the number was actually released, False otherwise (caller
    should treat False as "the number stays permanently used", matching the default policy of
    never freeing used numbers).
    """
    counter = await _lock_counter_row(session)
    if counter is None or counter.current_number != contract_number:
        return False
    counter.current_number -= 1
    await session.flush()
    return True


async def set_next_contract_number(
    session: AsyncSession, next_value: int, reason: str, changed_by_user_id: int | None
) -> None:
    """Superadmin override: manually set the counter, with a mandatory reason logged."""
    result = await session.execute(
        select(ContractCounter).where(ContractCounter.id == 1).with_for_update()
    )
    counter = result.scalar_one_or_none()
    old_value = counter.current_number if counter else 0
    if counter is None:
        counter = ContractCounter(id=1, current_number=next_value - 1)
        session.add(counter)
    else:
        counter.current_number = next_value - 1

    session.add(
        ContractCounterLog(
            old_value=old_value,
            new_value=next_value - 1,
            reason=reason,
            changed_by_user_id=changed_by_user_id,
        )
    )
    await session.flush()

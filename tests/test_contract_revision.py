from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.user import User
from app.database.repositories.counter_repo import (
    release_last_number_if_matches,
    reserve_next_contract_number,
)
from app.database.repositories.user_repo import get_role_by_code
from app.schemas.conditions import ContractConditions
from app.schemas.identity import IdentityExtraction
from app.services import quick_contract_service
from app.services.openai_service import OpenAIService

SOFFICE_AVAILABLE = shutil.which("soffice") is not None or shutil.which("soffice.exe") is not None
requires_soffice = pytest.mark.skipif(
    not SOFFICE_AVAILABLE, reason="LibreOffice (soffice) is not installed on this machine"
)


async def _manager(session: AsyncSession) -> User:
    role = await get_role_by_code(session, "manager")
    user = User(telegram_id=99, full_name="Test Manager", role_id=role.id)
    session.add(user)
    await session.flush()
    return user


async def _draft(session: AsyncSession):
    manager = await _manager(session)
    identity = IdentityExtraction(full_name="Тестов Тест Тестович", iin="010312500019")
    conditions = ContractConditions(service_type="снятие ареста от ЧСИ", amount_kzt=50000, payment_type="after_result")
    contract, client, _, _ = await quick_contract_service.generate_contract_immediately(
        session, openai_service=OpenAIService(), identity=identity, conditions=conditions, manager_id=manager.id
    )
    return contract, client


@requires_soffice
async def test_revise_contract_updates_only_mentioned_fields(db_session: AsyncSession) -> None:
    contract, client = await _draft(db_session)
    original_version = contract.version

    docx_path, pdf_path = await quick_contract_service.revise_contract_from_reply(
        db_session,
        openai_service=OpenAIService(),  # disabled in tests -> manual heuristics
        contract=contract,
        client=client,
        edit_text="Поменяй стоимость на 30000",
        edited_by_id=contract.manager_id,
    )

    assert contract.version == original_version + 1
    assert contract.amount == 30000
    assert Path(docx_path).exists()
    assert Path(pdf_path).exists()
    # payment_type must be untouched since the instruction never mentioned it
    conditions = ContractConditions.model_validate(contract.service_data)
    assert conditions.payment_type == "after_result"


@requires_soffice
async def test_revise_contract_remove_address(db_session: AsyncSession) -> None:
    contract, client = await _draft(db_session)
    client.address = "г. Талдыкорган, ул. Примерная, 1"
    await db_session.flush()

    await quick_contract_service.revise_contract_from_reply(
        db_session,
        openai_service=OpenAIService(),
        contract=contract,
        client=client,
        edit_text="Убери адрес",
        edited_by_id=contract.manager_id,
    )
    assert client.address is None


@requires_soffice
async def test_revise_signed_contract_raises(db_session: AsyncSession) -> None:
    contract, client = await _draft(db_session)
    contract.status = "signed"
    await db_session.flush()

    with pytest.raises(quick_contract_service.ContractAlreadySignedError):
        await quick_contract_service.revise_contract_from_reply(
            db_session,
            openai_service=OpenAIService(),
            contract=contract,
            client=client,
            edit_text="Поменяй стоимость на 1000",
            edited_by_id=contract.manager_id,
        )


@requires_soffice
async def test_revise_sent_for_signature_contract_raises(db_session: AsyncSession) -> None:
    """A signing link already points at a specific PDF - editing after that point would
    silently change what the client is about to sign, so it must be blocked too."""
    contract, client = await _draft(db_session)
    contract.status = "sent_for_signature"
    await db_session.flush()

    with pytest.raises(quick_contract_service.ContractAlreadySignedError):
        await quick_contract_service.revise_contract_from_reply(
            db_session,
            openai_service=OpenAIService(),
            contract=contract,
            client=client,
            edit_text="Поменяй стоимость на 1000",
            edited_by_id=contract.manager_id,
        )


@requires_soffice
async def test_quick_mode_contract_is_approved_immediately_with_no_review_stage(
    db_session: AsyncSession,
) -> None:
    """Quick mode has no separate 'Утвердить' step: creation and revision both leave the
    contract 'approved' (signature/stamp embedded) rather than bouncing through 'draft'/
    'review' the way the detailed mode's explicit-approval flow does."""
    contract, client = await _draft(db_session)
    assert contract.status == "approved"

    await quick_contract_service.revise_contract_from_reply(
        db_session,
        openai_service=OpenAIService(),
        contract=contract,
        client=client,
        edit_text="Поменяй стоимость на 40000",
        edited_by_id=contract.manager_id,
    )
    assert contract.status == "approved"


async def test_release_last_number_only_releases_most_recent(db_session: AsyncSession) -> None:
    first = await reserve_next_contract_number(db_session, start_value=1)
    second = await reserve_next_contract_number(db_session, start_value=1)
    await db_session.commit()

    # releasing the first (non-last) number must be a no-op
    released_first = await release_last_number_if_matches(db_session, first)
    assert released_first is False

    released_second = await release_last_number_if_matches(db_session, second)
    assert released_second is True

    third = await reserve_next_contract_number(db_session, start_value=1)
    assert third == second  # the released number is reused, no gap created

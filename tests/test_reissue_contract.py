from __future__ import annotations

import shutil

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.user import User
from app.database.repositories.user_repo import get_role_by_code
from app.schemas.conditions import ContractConditions
from app.schemas.identity import IdentityExtraction
from app.services import quick_contract_service
from app.services.openai_service import OpenAIService
from scripts.reissue_contract import ContractNotReissuableError, reissue_contract

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
    conditions = ContractConditions(
        service_type="снятие ареста от ЧСИ", amount_kzt=50000, payment_type="after_result"
    )
    contract, client, _, _ = await quick_contract_service.generate_contract_immediately(
        session, openai_service=OpenAIService(), identity=identity, conditions=conditions, manager_id=manager.id
    )
    return contract, client, manager


@requires_soffice
async def test_reissue_bumps_version_and_leaves_terms_untouched(db_session: AsyncSession) -> None:
    contract, _client, manager = await _draft(db_session)
    original_version = contract.version
    original_amount = contract.amount
    original_payment_type = contract.payment_type

    docx_path, pdf_path = await reissue_contract(
        db_session, contract_number=contract.contract_number, approved_by_telegram_id=manager.telegram_id
    )

    assert contract.version == original_version + 1
    assert contract.amount == original_amount
    assert contract.payment_type == original_payment_type
    assert f"final_v{contract.version}.docx" in docx_path
    assert f"final_v{contract.version}.pdf" in pdf_path


@requires_soffice
async def test_reissue_signed_contract_raises(db_session: AsyncSession) -> None:
    contract, _client, manager = await _draft(db_session)
    contract.status = "signed"
    await db_session.flush()

    with pytest.raises(ContractNotReissuableError):
        await reissue_contract(
            db_session, contract_number=contract.contract_number, approved_by_telegram_id=manager.telegram_id
        )


async def test_reissue_missing_contract_raises(db_session: AsyncSession) -> None:
    with pytest.raises(ContractNotReissuableError):
        await reissue_contract(db_session, contract_number=999999)

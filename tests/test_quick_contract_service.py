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

SOFFICE_AVAILABLE = shutil.which("soffice") is not None or shutil.which("soffice.exe") is not None


def _identity(**overrides) -> IdentityExtraction:
    base = dict(full_name="СЕЙТЖАНОВ АЙБЕК НҰРЛАНҰЛЫ", iin="010312500019")
    base.update(overrides)
    return IdentityExtraction(**base)


def _conditions(**overrides) -> ContractConditions:
    base = dict(service_type="снятие ареста от ЧСИ", amount_kzt=50000, payment_type="after_result")
    base.update(overrides)
    return ContractConditions(**base)


async def _manager(session: AsyncSession) -> User:
    role = await get_role_by_code(session, "manager")
    user = User(telegram_id=42, full_name="Test Manager", role_id=role.id)
    session.add(user)
    await session.flush()
    return user


def test_no_missing_fields_when_everything_present() -> None:
    missing = quick_contract_service.detect_missing_required_fields(
        _identity(), _conditions(), require_phone=False
    )
    assert missing == []


def test_missing_amount_and_payment_type() -> None:
    conditions = _conditions(amount_kzt=None, payment_type="custom")
    missing = quick_contract_service.detect_missing_required_fields(
        _identity(), conditions, require_phone=False
    )
    assert "amount" in missing
    assert "payment_type" in missing


def test_missing_full_name_and_iin() -> None:
    identity = IdentityExtraction(full_name=None, iin=None)
    missing = quick_contract_service.detect_missing_required_fields(
        identity, _conditions(), require_phone=False
    )
    assert "full_name" in missing
    assert "iin" in missing


def test_phone_only_required_when_configured() -> None:
    conditions = _conditions(client_phone=None)
    assert "phone" not in quick_contract_service.detect_missing_required_fields(
        _identity(), conditions, require_phone=False
    )
    assert "phone" in quick_contract_service.detect_missing_required_fields(
        _identity(), conditions, require_phone=True
    )


def test_does_not_ask_about_birth_date_address_or_document_number() -> None:
    """The quick flow must never block on fields the spec explicitly excludes."""
    identity = IdentityExtraction(full_name="Иванов Иван", iin="010312500019", birth_date=None)
    missing = quick_contract_service.detect_missing_required_fields(
        identity, _conditions(), require_phone=False
    )
    assert "birth_date" not in missing
    assert "address" not in missing
    assert "document_number" not in missing


def test_clarification_message_format() -> None:
    text = quick_contract_service.build_clarification_message(["amount", "payment_type"])
    assert text.startswith("Не хватает данных")
    assert "1." in text and "2." in text
    assert "Стоимость" in text


def test_build_display_filename_includes_number_client_and_amount() -> None:
    name = quick_contract_service.build_display_filename(
        contract_number=9, client_full_name="Турсынбаев Досжан Ташенович", amount_kzt=20000
    )
    assert name == "Договор оказания услуг № 9 Турсынбаев Досжан Ташенович 20000 тенге"


def test_build_display_filename_handles_missing_amount() -> None:
    name = quick_contract_service.build_display_filename(
        contract_number=1, client_full_name="Иванов Иван", amount_kzt=None
    )
    assert "сумма не указана" in name


def test_build_display_filename_strips_filesystem_forbidden_characters() -> None:
    name = quick_contract_service.build_display_filename(
        contract_number=1, client_full_name='Ива:нов/Иван*?"<>|', amount_kzt=5000
    )
    for char in '\\/:*?"<>|':
        assert char not in name


def test_manual_answer_heuristics_extract_amount_and_payment() -> None:
    conditions = _conditions(amount_kzt=None, payment_type="custom")
    merged = quick_contract_service._apply_manual_answer_heuristics(
        conditions, "50 000 тенге, оплата после результата"
    )
    assert merged.amount_kzt == 50000
    assert merged.payment_type == "after_result"


def test_manual_answer_heuristics_supports_short_k_amount() -> None:
    merged = quick_contract_service._apply_manual_answer_heuristics(
        _conditions(amount_kzt=None, payment_type="custom"),
        "60К, оплата сразу",
    )
    assert merged.amount_kzt == 60000
    assert merged.payment_type == "prepayment"


def test_manual_answer_heuristics_does_not_treat_phone_as_amount() -> None:
    merged = quick_contract_service._apply_manual_answer_heuristics(
        _conditions(amount_kzt=None, payment_type="custom"),
        "+7 700 000 00 00, стоимость 60К, оплата после результата",
    )
    assert merged.amount_kzt == 60000


async def test_explicit_text_identity_wins_over_ai_interpretation() -> None:
    class FakeOpenAI:
        is_enabled = True

        async def extract_identity_from_text(self, *, employee_text: str) -> IdentityExtraction:
            return IdentityExtraction(full_name="ОШИБОЧНОЕ ИМЯ", iin="000000000000")

        async def extract_contract_conditions(
            self, *, employee_text: str
        ) -> ContractConditions:
            return _conditions()

    identity, _ = await quick_contract_service.extract_identity_and_conditions_from_text(
        FakeOpenAI(),  # type: ignore[arg-type]
        text="ФИО: ТЮ ОЛЕГ ВИКТОРОВИЧ, ИИН: 731121302594; снятие ареста, 60К",
    )
    assert identity.full_name == "ТЮ ОЛЕГ ВИКТОРОВИЧ"
    assert identity.iin == "731121302594"


def test_manual_edit_instruction_heuristics_amount() -> None:
    edit = quick_contract_service._manual_edit_instruction_heuristics("Поменяй стоимость на 30000")
    assert edit.amount_kzt == 30000


def test_manual_edit_instruction_heuristics_payment() -> None:
    edit = quick_contract_service._manual_edit_instruction_heuristics(
        "Оплата не сразу, а после результата"
    )
    assert edit.payment_type == "after_result"


def test_manual_edit_instruction_heuristics_remove_address() -> None:
    edit = quick_contract_service._manual_edit_instruction_heuristics("Убери адрес")
    assert edit.remove_address is True


def test_merge_conditions_prefers_new_non_default_values() -> None:
    old = _conditions(amount_kzt=50000, payment_type="after_result")
    new = ContractConditions(service_type="", amount_kzt=70000, payment_type="custom")
    merged = quick_contract_service._merge_conditions(old, new)
    assert merged.amount_kzt == 70000  # explicitly mentioned -> overwritten
    assert merged.payment_type == "after_result"  # "custom" from `new` never overwrites


@pytest.mark.skipif(not SOFFICE_AVAILABLE, reason="LibreOffice (soffice) is not installed on this machine")
async def test_generate_contract_immediately_produces_final_signed_document(db_session: AsyncSession) -> None:
    """Quick mode has no separate 'Утвердить' step: the contract must come out already
    approved, with the executor's signature/stamp embedded and no draft watermark."""
    from pathlib import Path

    from docx import Document as DocxReader
    from pypdf import PdfReader

    manager = await _manager(db_session)
    identity = _identity()
    conditions = _conditions()

    contract, client, docx_path, pdf_path = await quick_contract_service.generate_contract_immediately(
        db_session, openai_service=OpenAIService(), identity=identity, conditions=conditions, manager_id=manager.id
    )

    assert contract.contract_number >= 1
    assert contract.status == "approved"
    assert contract.approved_by_id == manager.id
    assert contract.document_sha256
    assert client.full_name == identity.full_name
    assert Path(docx_path).exists()
    assert Path(pdf_path).exists()

    # regression guard: `approved_at` is stored in a naive TIMESTAMP WITHOUT TIME ZONE
    # column. A timezone-aware datetime slipping in here passes silently on SQLite (used by
    # this test suite) but asyncpg/PostgreSQL rejects it outright at INSERT/UPDATE time with
    # "can't subtract offset-naive and offset-aware datetimes" - exactly what happened in
    # production before this assertion was added.
    assert contract.approved_at.tzinfo is None

    # signature + seal must already be embedded as one fixed-layout composition
    assert len(DocxReader(docx_path).inline_shapes) == 1

    # and no "draft" watermark anywhere on the final PDF
    reader = PdfReader(pdf_path)
    full_text = "".join(page.extract_text() or "" for page in reader.pages)
    assert "ЧЕРНОВИК" not in full_text


async def test_process_quick_contract_message_manual_mode_missing_fields(db_session: AsyncSession) -> None:
    manager = await _manager(db_session)
    disabled_openai = OpenAIService()  # no API key configured in the test environment
    assert disabled_openai.is_enabled is False

    outcome = await quick_contract_service.process_quick_contract_message(
        db_session,
        openai_service=disabled_openai,
        image_bytes=b"fake-image-bytes",
        mime_type="image/jpeg",
        caption="снятие ареста от ЧСИ",
        manager_id=manager.id,
    )

    # manual mode never extracts identity/amount from the image, so both are missing
    assert "full_name" in outcome.missing_fields
    assert "iin" in outcome.missing_fields
    assert "amount" in outcome.missing_fields
    assert outcome.pending_payload is not None


async def test_text_flow_accepts_fio_iin_and_requests_only_conditions(
    db_session: AsyncSession,
) -> None:
    manager = await _manager(db_session)
    outcome = await quick_contract_service.process_quick_contract_text(
        db_session,
        openai_service=OpenAIService(),
        text="ФИО: ТЮ ОЛЕГ ВИКТОРОВИЧ, ИИН: 731121302594",
        manager_id=manager.id,
    )
    assert "full_name" not in outcome.missing_fields
    assert "iin" not in outcome.missing_fields
    assert "service_type" in outcome.missing_fields
    assert "amount" in outcome.missing_fields
    assert "payment_type" in outcome.missing_fields


async def test_clarification_can_repair_missing_identity_without_ai(
    db_session: AsyncSession,
) -> None:
    manager = await _manager(db_session)
    pending = {
        "identity": IdentityExtraction().model_dump(),
        "conditions": _conditions().model_dump(),
        "manager_id": manager.id,
    }
    outcome = await quick_contract_service.merge_clarification_answer(
        db_session,
        openai_service=OpenAIService(),
        pending=pending,
        answer_text="ФИО: ТЮ ОЛЕГ ВИКТОРОВИЧ, ИИН: 731121302594",
    )
    assert "full_name" not in outcome.missing_fields
    assert "iin" not in outcome.missing_fields

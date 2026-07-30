from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.schemas.objection import NotarialWritExtraction, ObjectionSupplement
from app.services import objection_service
from app.utils.validators import gender_from_iin

SOFFICE_AVAILABLE = shutil.which("soffice") is not None or shutil.which("soffice.exe") is not None
requires_soffice = pytest.mark.skipif(
    not SOFFICE_AVAILABLE, reason="LibreOffice (soffice) is not installed on this machine"
)

FEMALE_IIN = "930922400071"  # synthetic test IIN: even 7th digit -> female
MALE_IIN = "010312500019"  # synthetic test IIN: odd 7th digit -> male


def _writ(**overrides) -> NotarialWritExtraction:
    base = dict(
        unique_number="08251-009999/000",
        registry_number="9999",
        writ_date="15.02.2026",
        notary_city="Астана",
        notary_full_name="ЖҰМАБЕКОВ ДАНИЯР СЕРІКҰЛЫ",
        notary_license_number="00000001",
        notary_license_date="01.01.2020",
        debtor_last_name="ТӨЛЕУОВА",
        debtor_first_name="АЙГЕРІМ",
        debtor_middle_name="САПАРҚЫЗЫ",
        debtor_birth_date="22.09.1993",
        debtor_iin=FEMALE_IIN,
        debtor_address="КАЗАХСТАН, Г. КОКШЕТАУ",
        creditor_name_nominative='Акционерное общество "Народный Банк Казахстана"',
        creditor_name_genitive='Акционерного общества "Народный Банк Казахстана"',
        creditor_bin="940140000385",
        debt_amount=2163183.6,
        fee_amount=22542,
        total_amount=2185725.6,
    )
    base.update(overrides)
    return NotarialWritExtraction(**base)


def test_gender_from_iin_matches_real_samples() -> None:
    assert gender_from_iin(FEMALE_IIN) == "female"
    assert gender_from_iin(MALE_IIN) == "male"


def test_format_amount_tenge_whole_number() -> None:
    assert objection_service.format_amount_tenge(707043) == "707 043 тенге"


def test_format_amount_tenge_with_decimals() -> None:
    assert objection_service.format_amount_tenge(2163183.6) == "2 163 183,60 тенге"


def test_format_amount_tenge_none() -> None:
    assert objection_service.format_amount_tenge(None) == "0 тенге"


def test_no_missing_fields_when_everything_present() -> None:
    missing = objection_service.detect_missing_required_fields(_writ(), "+7 701 987 6543")
    assert missing == []


def test_missing_phone_and_iin() -> None:
    writ = _writ(debtor_iin=None)
    missing = objection_service.detect_missing_required_fields(writ, None)
    assert "debtor_iin" in missing
    assert "client_phone" in missing


def test_missing_creditor_and_amount() -> None:
    writ = _writ(creditor_name_nominative=None, creditor_name_genitive=None, total_amount=None)
    missing = objection_service.detect_missing_required_fields(writ, "+7 700 000 0000")
    assert "creditor_name" in missing
    assert "total_amount" in missing


def test_clarification_message_lists_missing_fields() -> None:
    text = objection_service.build_clarification_message(["debtor_iin", "client_phone"])
    assert text.startswith("Не хватает данных")
    assert "1." in text and "2." in text


def test_build_render_context_female_gender() -> None:
    ctx = objection_service.build_render_context(
        writ=_writ(), client_phone="+7 701 987 6543", client_email=None
    )
    assert "не согласна" in ctx["disagree_clause"]
    assert "не подписывала" in ctx["not_signed_clause"]
    assert "я узнала" in ctx["learned_clause"]
    assert ctx["client_signature_line"] == "Төлеуова А.С."
    assert ctx["writ_date_long"] == "15 февраля 2026 года"
    assert ctx["client_email_line"] == ""
    assert "по договору" not in ctx["obligation_paragraph"]  # none supplied -> empty
    assert ctx["obligation_paragraph"] == ""


def test_build_render_context_male_gender() -> None:
    ctx = objection_service.build_render_context(
        writ=_writ(debtor_iin=MALE_IIN), client_phone="+7 701 709 1121", client_email=None
    )
    assert "не согласен" in ctx["disagree_clause"]
    assert "не подписывал" in ctx["not_signed_clause"]
    assert "я узнал" in ctx["learned_clause"]


def test_build_render_context_includes_obligation_paragraph_when_present() -> None:
    writ = _writ(obligation_basis_clause="по договору банковского займа №CPA000016337588 от 22.09.2025")
    ctx = objection_service.build_render_context(writ=writ, client_phone="+7 700 000 0000", client_email=None)
    assert "CPA000016337588" in ctx["obligation_paragraph"]
    assert "требуют проверки в судебном порядке" in ctx["obligation_paragraph"]


def test_build_render_context_includes_email_line_when_present() -> None:
    ctx = objection_service.build_render_context(
        writ=_writ(), client_phone="+7 700 000 0000", client_email="client@example.com"
    )
    assert "client@example.com" in ctx["client_email_line"]


def test_build_render_context_raises_without_valid_iin() -> None:
    with pytest.raises(objection_service.MissingGenderError):
        objection_service.build_render_context(
            writ=_writ(debtor_iin=None), client_phone="+7 700 000 0000", client_email=None
        )


def test_apply_supplement_overwrites_only_mentioned_fields() -> None:
    writ = _writ(unique_number=None, registry_number=None)
    supplement = ObjectionSupplement(unique_number="08251-009999/000", registry_number="9999")
    updated = objection_service.apply_supplement(writ, supplement)
    assert updated.unique_number == "08251-009999/000"
    assert updated.registry_number == "9999"
    # untouched fields survive
    assert updated.notary_city == writ.notary_city


def test_build_display_filename_is_deterministic_and_safe() -> None:
    name = objection_service.build_display_filename(
        debtor_last_name="ТӨЛЕУОВА", client_phone="+7 701 987 6543"
    )
    assert name.startswith("Возражение_Төлеуова_77019876543_")
    for char in '\\/:*?"<>|':
        assert char not in name


@requires_soffice
async def test_generate_objection_files_creates_docx_and_pdf(tmp_path: Path) -> None:
    docx_path, pdf_path = await objection_service.generate_objection_files(
        writ=_writ(), client_phone="+7 701 987 6543", client_email=None
    )
    assert Path(docx_path).exists()
    assert Path(pdf_path).exists()


async def test_process_objection_message_manual_mode_missing_fields() -> None:
    from app.services.openai_service import OpenAIService

    disabled_openai = OpenAIService()
    assert disabled_openai.is_enabled is False

    outcome = await objection_service.process_objection_message(
        disabled_openai,
        image_bytes=b"fake-image-bytes",
        mime_type="image/jpeg",
        caption="+7 701 987 6543",
    )
    # manual mode never extracts writ fields from the image, so most are missing
    assert "debtor_iin" in outcome.missing_fields
    assert "client_phone" not in outcome.missing_fields  # parsed from caption via regex
    assert outcome.pending_payload is not None

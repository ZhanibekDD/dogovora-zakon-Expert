from __future__ import annotations

from app.schemas.identity import IdentityExtraction
from app.services.identity_text_service import (
    merge_identity,
    parse_identity_from_text,
    text_without_identity,
)


def test_parses_labelled_identity() -> None:
    identity = parse_identity_from_text(
        "ФИО: ТЮ ОЛЕГ ВИКТОРОВИЧ, ИИН: 731121302594; снятие ареста"
    )
    assert identity.full_name == "ТЮ ОЛЕГ ВИКТОРОВИЧ"
    assert identity.last_name == "ТЮ"
    assert identity.first_name == "ОЛЕГ"
    assert identity.middle_name == "ВИКТОРОВИЧ"
    assert identity.iin == "731121302594"


def test_parses_unlabelled_name_immediately_before_iin() -> None:
    identity = parse_identity_from_text(
        "ТЮ ОЛЕГ ВИКТОРОВИЧ 731121302594, снятие ареста, 60К"
    )
    assert identity.full_name == "ТЮ ОЛЕГ ВИКТОРОВИЧ"
    assert identity.iin == "731121302594"


def test_does_not_guess_name_from_service_text() -> None:
    identity = parse_identity_from_text("снятие ареста и отмена исполнительной надписи")
    assert identity.full_name is None
    assert identity.iin is None


def test_merge_identity_only_fills_missing_fields() -> None:
    original = IdentityExtraction(full_name="ИВАНОВ ИВАН", iin=None)
    supplement = IdentityExtraction(full_name="ДРУГОЕ ИМЯ", iin="731121302594")
    merged = merge_identity(original, supplement)
    assert merged.full_name == "ИВАНОВ ИВАН"
    assert merged.iin == "731121302594"


def test_text_without_identity_keeps_contract_terms() -> None:
    remainder = text_without_identity(
        "ФИО: ТЮ ОЛЕГ ВИКТОРОВИЧ, ИИН: 731121302594; снятие ареста, 60К"
    )
    assert "731121302594" not in remainder
    assert "ТЮ ОЛЕГ ВИКТОРОВИЧ" not in remainder
    assert "снятие ареста" in remainder

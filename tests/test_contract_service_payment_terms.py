from __future__ import annotations

from app.schemas.conditions import ContractConditions
from app.services.contract_service import build_payment_terms


def test_after_result_payment_points_to_result_clause() -> None:
    conditions = ContractConditions(service_type="test", payment_type="after_result")
    text = build_payment_terms(conditions)
    assert "п. 1.3" in text
    assert "п. 2.1" not in text


def test_split_payment_points_to_result_clause() -> None:
    conditions = ContractConditions(
        service_type="test",
        payment_type="split",
        first_payment_kzt=75_000,
        second_payment_kzt=75_000,
    )
    text = build_payment_terms(conditions)
    assert "75 000" in text
    assert "п. 1.3" in text
    assert "п. 2.1" not in text

from __future__ import annotations

from app.schemas.conditions import ContractConditions
from app.services.contract_service import (
    DEFAULT_WORK_PERIOD,
    build_payment_terms,
    normalize_work_period,
)


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


def test_default_work_period_preserves_start_conditions() -> None:
    assert normalize_work_period(None) == DEFAULT_WORK_PERIOD
    assert "полного комплекта документов" in normalize_work_period(None)
    assert "оплаты" in normalize_work_period(None)


def test_custom_work_period_is_not_rewritten() -> None:
    assert normalize_work_period("14 рабочих дней после оплаты") == "14 рабочих дней после оплаты"

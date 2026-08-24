from __future__ import annotations

from types import SimpleNamespace

from app.api.routes.signing import _contract_summary, _payment_requisites
from app.services.contract_service import DEFAULT_WORK_PERIOD


def test_signing_summary_uses_frozen_rendered_period() -> None:
    contract = SimpleNamespace(
        service_data={
            "work_period": "live fallback that must not win",
            "signing_snapshot": {"work_period": "30 дней после документов и оплаты"},
        },
        amount=150_000,
        payment_type="prepayment",
    )

    assert _contract_summary(contract)["period"] == "30 дней после документов и оплаты"


def test_legacy_signing_summary_uses_render_normalization() -> None:
    contract = SimpleNamespace(service_data={}, amount=150_000, payment_type="prepayment")

    assert _contract_summary(contract)["period"] == DEFAULT_WORK_PERIOD


def test_payment_requisites_come_only_from_contract_snapshot() -> None:
    contract = SimpleNamespace(
        service_data={
            "signing_snapshot": {
                "payment_requisites": {
                    "recipient": "Frozen recipient",
                    "bank_name": "Frozen bank",
                    "kaspi_number": "+7 700 000 00 00",
                }
            }
        }
    )

    assert _payment_requisites(contract) == {
        "recipient": "Frozen recipient",
        "bank_name": "Frozen bank",
        "kaspi_number": "+7 700 000 00 00",
    }


def test_payment_requisites_are_omitted_without_complete_snapshot() -> None:
    legacy = SimpleNamespace(service_data={})
    incomplete = SimpleNamespace(
        service_data={
            "signing_snapshot": {
                "payment_requisites": {
                    "recipient": "Recipient",
                    "bank_name": "Bank",
                }
            }
        }
    )

    assert _payment_requisites(legacy) is None
    assert _payment_requisites(incomplete) is None

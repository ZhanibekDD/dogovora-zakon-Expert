from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace

from app.services.crm_sync_service import build_contract_payload


def test_build_contract_payload_contains_client_and_contract_identity() -> None:
    client = SimpleNamespace(
        id=77,
        full_name="Иванов Иван Иванович",
        iin="900101300123",
        phone="+77001234567",
        address="г. Алматы",
        document_number="123456789",
    )
    contract = SimpleNamespace(
        id=501,
        contract_number=741,
        approved_at=datetime.datetime(2026, 8, 31, 12, 30),
        created_at=datetime.datetime(2026, 8, 31, 12, 0),
        amount=Decimal("50000.00"),
        currency="KZT",
        payment_type="prepayment",
        payment_status="pending",
        status="approved",
        document_sha256="abc123",
        pdf_path="/private/final.pdf",
        docx_path="/private/final.docx",
        service_data={
            "service_type": "Снятие ареста",
            "service_details": ["Подготовка заявления"],
            "client_phone": "+77009998877",
        },
    )

    payload = build_contract_payload(contract, client)
    assert payload["externalContractId"] == "dogovora:501"
    assert payload["generatorContractId"] == 501
    assert payload["number"] == "741"
    assert payload["amount"] == 50000.0
    assert payload["service"] == "Снятие ареста"
    assert payload["hasPdf"] is True
    assert payload["hasDocx"] is True
    assert payload["client"]["externalClientId"] == "dogovora:77"
    assert payload["client"]["iin"] == "900101300123"
    assert payload["client"]["phone"] == "+77009998877"
    assert "pdf_path" not in payload
    assert "docx_path" not in payload

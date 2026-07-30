from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PaymentTypeLiteral = Literal["prepayment", "after_result", "split", "already_paid", "custom"]


class ContractConditions(BaseModel):
    """Mirrors the JSON Schema sent to the OpenAI Responses API for free-text condition extraction."""

    service_type: str
    service_details: list[str] = Field(default_factory=list)
    amount_kzt: int | None = None
    payment_type: PaymentTypeLiteral = "custom"
    first_payment_kzt: int | None = None
    second_payment_kzt: int | None = None
    payment_deadline: str | None = None
    work_period: str | None = None
    client_phone: str | None = None
    bank_name: str | None = None
    creditor_name: str | None = None
    notary_name: str | None = None
    chsi_name: str | None = None
    enforcement_case_number: str | None = None
    result_definition: str | None = None
    additional_conditions: list[str] = Field(default_factory=list)
    template_code: str | None = None
    warnings: list[str] = Field(default_factory=list)

    # Populated after extraction by a separate drafting call (see
    # openai_service.draft_contract_narrative) — never part of the extraction JSON schema
    # below, so OpenAI never sees or fills these directly. Case-specific rewrites of the
    # approved template's clauses 1.1/1.2; None means "use the generic preset text as-is".
    subject_paragraph: str | None = None
    actions_paragraph: str | None = None


CONDITIONS_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "service_type": {"type": "string"},
        "service_details": {"type": "array", "items": {"type": "string"}},
        "amount_kzt": {"type": ["integer", "null"]},
        "payment_type": {
            "type": "string",
            "enum": ["prepayment", "after_result", "split", "already_paid", "custom"],
        },
        "first_payment_kzt": {"type": ["integer", "null"]},
        "second_payment_kzt": {"type": ["integer", "null"]},
        "payment_deadline": {"type": ["string", "null"]},
        "work_period": {"type": ["string", "null"]},
        "client_phone": {"type": ["string", "null"]},
        "bank_name": {"type": ["string", "null"]},
        "creditor_name": {"type": ["string", "null"]},
        "notary_name": {"type": ["string", "null"]},
        "chsi_name": {"type": ["string", "null"]},
        "enforcement_case_number": {"type": ["string", "null"]},
        "result_definition": {"type": ["string", "null"]},
        "additional_conditions": {"type": "array", "items": {"type": "string"}},
        "template_code": {"type": ["string", "null"]},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "service_type",
        "service_details",
        "amount_kzt",
        "payment_type",
        "first_payment_kzt",
        "second_payment_kzt",
        "payment_deadline",
        "work_period",
        "client_phone",
        "bank_name",
        "creditor_name",
        "notary_name",
        "chsi_name",
        "enforcement_case_number",
        "result_definition",
        "additional_conditions",
        "template_code",
        "warnings",
    ],
    "additionalProperties": False,
}

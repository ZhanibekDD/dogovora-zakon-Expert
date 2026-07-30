from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PaymentTypeLiteral = Literal["prepayment", "after_result", "split", "already_paid", "custom"]


class ContractEditInstruction(BaseModel):
    """A targeted change to an already-generated draft, extracted from one short reply
    message (e.g. "Поменяй стоимость на 30000"). Every field is nullable/empty by default:
    only fields the employee actually mentioned should come back populated, everything else
    must be left untouched so re-generating the draft never silently discards prior data.
    """

    amount_kzt: int | None = None
    payment_type: PaymentTypeLiteral | None = None
    first_payment_kzt: int | None = None
    second_payment_kzt: int | None = None
    work_period: str | None = None
    client_phone: str | None = None
    additional_service_details: list[str] = Field(default_factory=list)
    result_definition: str | None = None
    template_code: str | None = None
    remove_address: bool = False
    remove_client_phone: bool = False
    warnings: list[str] = Field(default_factory=list)


EDIT_INSTRUCTION_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "amount_kzt": {"type": ["integer", "null"]},
        "payment_type": {
            "type": ["string", "null"],
            "enum": ["prepayment", "after_result", "split", "already_paid", "custom", None],
        },
        "first_payment_kzt": {"type": ["integer", "null"]},
        "second_payment_kzt": {"type": ["integer", "null"]},
        "work_period": {"type": ["string", "null"]},
        "client_phone": {"type": ["string", "null"]},
        "additional_service_details": {"type": "array", "items": {"type": "string"}},
        "result_definition": {"type": ["string", "null"]},
        "template_code": {"type": ["string", "null"]},
        "remove_address": {"type": "boolean"},
        "remove_client_phone": {"type": "boolean"},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "amount_kzt",
        "payment_type",
        "first_payment_kzt",
        "second_payment_kzt",
        "work_period",
        "client_phone",
        "additional_service_details",
        "result_definition",
        "template_code",
        "remove_address",
        "remove_client_phone",
        "warnings",
    ],
    "additionalProperties": False,
}

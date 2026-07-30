from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.utils.validators import is_valid_date_format, is_valid_iin_format


class NotarialWritExtraction(BaseModel):
    """Fields extracted from a photographed/scanned 'Исполнительная надпись' (notarial writ
    of execution) - the source document a debtor brings in, from which an objection against
    that writ is drafted. Every field is nullable by design: never invent what isn't legible.
    """

    unique_number: str | None = None  # "08251-009999/000"
    registry_number: str | None = None  # "9999"
    writ_date: str | None = None  # DD.MM.YYYY

    notary_city: str | None = None
    notary_full_name: str | None = None
    notary_license_number: str | None = None
    notary_license_date: str | None = None  # DD.MM.YYYY

    debtor_last_name: str | None = None
    debtor_first_name: str | None = None
    debtor_middle_name: str | None = None
    debtor_birth_date: str | None = None  # DD.MM.YYYY
    debtor_iin: str | None = None
    debtor_address: str | None = None

    creditor_name_nominative: str | None = None  # as printed on the writ, e.g. exact legal form + name
    creditor_name_genitive: str | None = None  # ready-to-use genitive form for "в пользу ..."
    creditor_bin: str | None = None

    debt_amount: float | None = None
    fee_amount: float | None = None
    total_amount: float | None = None

    obligation_basis_clause: str | None = None  # e.g. "по договору банковского займа №CPA000016337588 от 22.09.2025"

    confidence: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("debtor_iin")
    @classmethod
    def _validate_iin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        digits = "".join(ch for ch in value if ch.isdigit())
        if not is_valid_iin_format(digits):
            raise ValueError("ИИН должен содержать ровно 12 цифр")
        return digits

    @field_validator("writ_date", "notary_license_date", "debtor_birth_date")
    @classmethod
    def _validate_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not is_valid_date_format(value):
            raise ValueError("Дата должна быть в формате DD.MM.YYYY")
        return value

    @property
    def debtor_full_name(self) -> str:
        parts = [self.debtor_last_name, self.debtor_first_name, self.debtor_middle_name]
        return " ".join(p for p in parts if p)


NOTARIAL_WRIT_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "unique_number": {"type": ["string", "null"]},
        "registry_number": {"type": ["string", "null"]},
        "writ_date": {"type": ["string", "null"]},
        "notary_city": {"type": ["string", "null"]},
        "notary_full_name": {"type": ["string", "null"]},
        "notary_license_number": {"type": ["string", "null"]},
        "notary_license_date": {"type": ["string", "null"]},
        "debtor_last_name": {"type": ["string", "null"]},
        "debtor_first_name": {"type": ["string", "null"]},
        "debtor_middle_name": {"type": ["string", "null"]},
        "debtor_birth_date": {"type": ["string", "null"]},
        "debtor_iin": {"type": ["string", "null"]},
        "debtor_address": {"type": ["string", "null"]},
        "creditor_name_nominative": {"type": ["string", "null"]},
        "creditor_name_genitive": {"type": ["string", "null"]},
        "creditor_bin": {"type": ["string", "null"]},
        "debt_amount": {"type": ["number", "null"]},
        "fee_amount": {"type": ["number", "null"]},
        "total_amount": {"type": ["number", "null"]},
        "obligation_basis_clause": {"type": ["string", "null"]},
        "confidence": {
            "type": "object",
            "properties": {
                "debtor_iin": {"type": "number"},
                "amounts": {"type": "number"},
            },
            "required": ["debtor_iin", "amounts"],
            "additionalProperties": False,
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "unique_number", "registry_number", "writ_date",
        "notary_city", "notary_full_name", "notary_license_number", "notary_license_date",
        "debtor_last_name", "debtor_first_name", "debtor_middle_name", "debtor_birth_date",
        "debtor_iin", "debtor_address",
        "creditor_name_nominative", "creditor_name_genitive", "creditor_bin",
        "debt_amount", "fee_amount", "total_amount", "obligation_basis_clause",
        "confidence", "warnings",
    ],
    "additionalProperties": False,
}


class ObjectionSupplement(BaseModel):
    """Free-text supplement used to fill in whatever the vision extraction missed, merged
    into the original NotarialWritExtraction - plus client_phone/client_email, which never
    appear on the writ itself and only ever come from the employee. Only fields the employee
    actually mentioned should come back populated; everything else stays null so it never
    overwrites already-known data."""

    client_phone: str | None = None
    client_email: str | None = None
    unique_number: str | None = None
    registry_number: str | None = None
    writ_date: str | None = None
    notary_city: str | None = None
    notary_full_name: str | None = None
    notary_license_number: str | None = None
    notary_license_date: str | None = None
    debtor_last_name: str | None = None
    debtor_first_name: str | None = None
    debtor_middle_name: str | None = None
    debtor_birth_date: str | None = None
    debtor_iin: str | None = None
    debtor_address: str | None = None
    creditor_name_nominative: str | None = None
    creditor_name_genitive: str | None = None
    creditor_bin: str | None = None
    debt_amount: float | None = None
    fee_amount: float | None = None
    total_amount: float | None = None
    obligation_basis_clause: str | None = None
    warnings: list[str] = Field(default_factory=list)

    @field_validator("debtor_iin")
    @classmethod
    def _validate_iin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        digits = "".join(ch for ch in value if ch.isdigit())
        if not is_valid_iin_format(digits):
            raise ValueError("ИИН должен содержать ровно 12 цифр")
        return digits

    @field_validator("writ_date", "notary_license_date", "debtor_birth_date")
    @classmethod
    def _validate_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not is_valid_date_format(value):
            raise ValueError("Дата должна быть в формате DD.MM.YYYY")
        return value


OBJECTION_SUPPLEMENT_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "client_phone": {"type": ["string", "null"]},
        "client_email": {"type": ["string", "null"]},
        "unique_number": {"type": ["string", "null"]},
        "registry_number": {"type": ["string", "null"]},
        "writ_date": {"type": ["string", "null"]},
        "notary_city": {"type": ["string", "null"]},
        "notary_full_name": {"type": ["string", "null"]},
        "notary_license_number": {"type": ["string", "null"]},
        "notary_license_date": {"type": ["string", "null"]},
        "debtor_last_name": {"type": ["string", "null"]},
        "debtor_first_name": {"type": ["string", "null"]},
        "debtor_middle_name": {"type": ["string", "null"]},
        "debtor_birth_date": {"type": ["string", "null"]},
        "debtor_iin": {"type": ["string", "null"]},
        "debtor_address": {"type": ["string", "null"]},
        "creditor_name_nominative": {"type": ["string", "null"]},
        "creditor_name_genitive": {"type": ["string", "null"]},
        "creditor_bin": {"type": ["string", "null"]},
        "debt_amount": {"type": ["number", "null"]},
        "fee_amount": {"type": ["number", "null"]},
        "total_amount": {"type": ["number", "null"]},
        "obligation_basis_clause": {"type": ["string", "null"]},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "client_phone", "client_email", "unique_number", "registry_number", "writ_date",
        "notary_city", "notary_full_name", "notary_license_number", "notary_license_date",
        "debtor_last_name", "debtor_first_name", "debtor_middle_name", "debtor_birth_date",
        "debtor_iin", "debtor_address", "creditor_name_nominative", "creditor_name_genitive",
        "creditor_bin", "debt_amount", "fee_amount", "total_amount", "obligation_basis_clause",
        "warnings",
    ],
    "additionalProperties": False,
}

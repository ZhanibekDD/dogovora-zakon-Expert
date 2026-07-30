from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.utils.validators import (
    iin_matches_birth_date,
    is_valid_date_format,
    is_valid_iin_format,
)


class ConfidenceScores(BaseModel):
    full_name: float = 0.0
    iin: float = 0.0
    birth_date: float = 0.0


class IdentityExtraction(BaseModel):
    """Mirrors the JSON Schema sent to the OpenAI Responses API for ID document extraction.

    Every field is nullable by design: the model must never invent a value it cannot
    actually read on the document image.
    """

    full_name: str | None = None
    last_name: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    iin: str | None = None
    birth_date: str | None = None
    document_number: str | None = None
    issue_date: str | None = None
    expiry_date: str | None = None
    birth_place: str | None = None
    confidence: ConfidenceScores = Field(default_factory=ConfidenceScores)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("iin")
    @classmethod
    def _validate_iin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        digits = "".join(ch for ch in value if ch.isdigit())
        if not is_valid_iin_format(digits):
            raise ValueError("ИИН должен содержать ровно 12 цифр")
        return digits

    @field_validator("birth_date", "issue_date", "expiry_date")
    @classmethod
    def _validate_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not is_valid_date_format(value):
            raise ValueError("Дата должна быть в формате DD.MM.YYYY")
        return value

    def requires_manual_review(self, min_confidence: float = 0.75) -> bool:
        if self.warnings:
            return True
        if self.iin and self.confidence.iin < min_confidence:
            return True
        if self.full_name and self.confidence.full_name < min_confidence:
            return True
        if self.birth_date and self.confidence.birth_date < min_confidence:
            return True
        return bool(
            self.iin and self.birth_date and not iin_matches_birth_date(self.iin, self.birth_date)
        )


IDENTITY_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "full_name": {"type": ["string", "null"]},
        "last_name": {"type": ["string", "null"]},
        "first_name": {"type": ["string", "null"]},
        "middle_name": {"type": ["string", "null"]},
        "iin": {"type": ["string", "null"]},
        "birth_date": {"type": ["string", "null"]},
        "document_number": {"type": ["string", "null"]},
        "issue_date": {"type": ["string", "null"]},
        "expiry_date": {"type": ["string", "null"]},
        "birth_place": {"type": ["string", "null"]},
        "confidence": {
            "type": "object",
            "properties": {
                "full_name": {"type": "number"},
                "iin": {"type": "number"},
                "birth_date": {"type": "number"},
            },
            "required": ["full_name", "iin", "birth_date"],
            "additionalProperties": False,
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "full_name",
        "last_name",
        "first_name",
        "middle_name",
        "iin",
        "birth_date",
        "document_number",
        "issue_date",
        "expiry_date",
        "birth_place",
        "confidence",
        "warnings",
    ],
    "additionalProperties": False,
}

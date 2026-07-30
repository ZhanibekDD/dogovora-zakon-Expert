from __future__ import annotations

from pydantic import BaseModel


class ContractNarrative(BaseModel):
    """A case-specific rewrite of the fixed clauses 1.1 (предмет договора) and 1.2 (состав
    услуг), produced by weaving the facts extracted from this particular case into the
    already-approved base wording. Mirrors the JSON Schema sent to the OpenAI Responses API."""

    subject_paragraph: str
    actions_paragraph: str


CONTRACT_NARRATIVE_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "subject_paragraph": {"type": "string"},
        "actions_paragraph": {"type": "string"},
    },
    "required": ["subject_paragraph", "actions_paragraph"],
    "additionalProperties": False,
}

from __future__ import annotations

import re

from app.schemas.identity import ConfidenceScores, IdentityExtraction
from app.utils.validators import is_valid_iin_format

_IIN_RE = re.compile(r"(?<!\d)((?:\d[\s-]?){12})(?!\d)")
_FIO_LABEL_RE = re.compile(
    r"(?:\bфио\b|\bф\.?\s*и\.?\s*о\.?\b)\s*[:=-]?\s*"
    r"(?P<name>.+?)(?=(?:\bии?н\b|[,;\n]|$))",
    re.IGNORECASE,
)
_NAME_TOKEN_RE = re.compile(
    r"[A-Za-zА-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]+"
    r"(?:[-'][A-Za-zА-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]+)*"
)
_NON_NAME_WORDS = {
    "клиент",
    "договор",
    "ийн",
    "иин",
    "услуга",
    "услуги",
    "оплата",
    "стоимость",
    "цена",
    "тенге",
    "телефон",
    "номер",
    "снятие",
    "отмена",
    "арест",
    "ареста",
    "чси",
    "нотариус",
    "суд",
}


def _normalise_iin(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    return digits if is_valid_iin_format(digits) else None


def _clean_name(raw: str) -> str | None:
    tokens = _NAME_TOKEN_RE.findall(raw)
    tokens = [token for token in tokens if token.lower() not in _NON_NAME_WORDS]
    if not 2 <= len(tokens) <= 6:
        return None
    return " ".join(tokens)


def _name_before_iin(text: str, iin_match: re.Match[str] | None) -> str | None:
    if iin_match is None:
        return None
    prefix = text[: iin_match.start()]
    segment = re.split(r"[,;\n]", prefix)[-1]
    segment = re.sub(r"(?:\bфио\b|\bф\.?\s*и\.?\s*о\.?\b)\s*[:=-]?", "", segment, flags=re.I)
    return _clean_name(segment)


def parse_identity_from_text(text: str) -> IdentityExtraction:
    """Extract explicitly written ФИО/ИИН without requiring an AI call.

    This parser intentionally stays conservative: it accepts a labelled ФИО or a short
    name immediately before a 12-digit ИИН and never guesses a name from the service text.
    OpenAI can enrich the result in production, but the Telegram flow remains usable when
    the API is temporarily unavailable.
    """

    source = (text or "").strip()
    iin_match = _IIN_RE.search(source)
    iin = _normalise_iin(iin_match.group(1)) if iin_match else None

    labelled = _FIO_LABEL_RE.search(source)
    full_name = _clean_name(labelled.group("name")) if labelled else None
    if full_name is None:
        full_name = _name_before_iin(source, iin_match)

    parts = full_name.split() if full_name else []
    return IdentityExtraction(
        full_name=full_name,
        last_name=parts[0] if len(parts) >= 1 else None,
        first_name=parts[1] if len(parts) >= 2 else None,
        middle_name=" ".join(parts[2:]) if len(parts) >= 3 else None,
        iin=iin,
        confidence=ConfidenceScores(
            full_name=1.0 if labelled and full_name else (0.9 if full_name else 0.0),
            iin=1.0 if iin else 0.0,
            birth_date=0.0,
        ),
    )


def merge_identity(primary: IdentityExtraction, supplement: IdentityExtraction) -> IdentityExtraction:
    """Fill only missing identity fields, preserving data already read from the ID card."""

    data = primary.model_dump()
    for field in (
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
    ):
        value = getattr(supplement, field)
        if not data.get(field) and value:
            data[field] = value

    confidence = primary.confidence.model_dump()
    for field in ("full_name", "iin", "birth_date"):
        confidence[field] = max(
            confidence.get(field, 0.0),
            getattr(supplement.confidence, field),
        )
    data["confidence"] = confidence
    data["warnings"] = list(dict.fromkeys([*primary.warnings, *supplement.warnings]))
    return IdentityExtraction.model_validate(data)


def text_without_identity(text: str) -> str:
    """Remove explicit ФИО/ИИН fragments before the manual service-condition fallback."""

    identity = parse_identity_from_text(text)
    cleaned = text or ""
    if identity.full_name:
        cleaned = re.sub(re.escape(identity.full_name), " ", cleaned, count=1, flags=re.I)
    cleaned = _IIN_RE.sub(" ", cleaned)
    cleaned = _FIO_LABEL_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\b(?:иин|iin)\b\s*[:=-]?", " ", cleaned, flags=re.I)
    return re.sub(r"\s+", " ", cleaned).strip(" ,;:-")

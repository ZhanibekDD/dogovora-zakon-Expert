from __future__ import annotations

import re

_PHONE_RE = re.compile(r"(\+?\d[\d ]{6,}\d)")
_IIN_RE = re.compile(r"\b\d{12}\b")


def mask_iin(iin: str | None) -> str:
    if not iin:
        return "—"
    digits = re.sub(r"\D", "", iin)
    if len(digits) != 12:
        return "*" * len(digits)
    return f"{digits[:6]}****{digits[-2:]}"


def mask_phone(phone: str | None) -> str:
    if not phone:
        return "—"
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 6:
        return "*" * len(digits)
    return f"+{digits[:1]}***{digits[-4:-2]}**{digits[-2:]}" if len(digits) > 10 else "***" + digits[-4:]


def mask_text(text: str) -> str:
    """Mask any 12-digit IIN-looking or phone-looking substrings found in free text before logging."""
    text = _IIN_RE.sub(lambda m: mask_iin(m.group(0)), text)
    text = _PHONE_RE.sub(lambda m: mask_phone(m.group(0)), text)
    return text

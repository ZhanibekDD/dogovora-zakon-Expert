from __future__ import annotations

import datetime
import re

IIN_RE = re.compile(r"^\d{12}$")
DATE_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")

_CENTURY_CODE = {
    "1": 1800,
    "2": 1800,
    "3": 1900,
    "4": 1900,
    "5": 2000,
    "6": 2000,
}


class ValidationError(Exception):
    pass


def is_valid_iin_format(iin: str) -> bool:
    return bool(IIN_RE.match(iin))


def is_valid_date_format(value: str) -> bool:
    return bool(DATE_RE.match(value))


def parse_ddmmyyyy(value: str) -> datetime.date:
    match = DATE_RE.match(value)
    if not match:
        raise ValidationError(f"Дата должна быть в формате DD.MM.YYYY: {value!r}")
    day, month, year = (int(part) for part in match.groups())
    return datetime.date(year, month, day)


def birth_date_from_iin(iin: str) -> datetime.date | None:
    """Derive the birth date encoded in the first 6 digits + century digit (7th) of a valid IIN."""
    if not is_valid_iin_format(iin):
        return None
    yy, mm, dd, century_digit = iin[0:2], iin[2:4], iin[4:6], iin[6]
    century = _CENTURY_CODE.get(century_digit)
    if century is None:
        return None
    try:
        return datetime.date(century + int(yy), int(mm), int(dd))
    except ValueError:
        return None


def iin_matches_birth_date(iin: str, birth_date: str) -> bool:
    """Cross-check that the birth date printed on the document matches the IIN encoding."""
    if not is_valid_iin_format(iin) or not is_valid_date_format(birth_date):
        return False
    encoded = birth_date_from_iin(iin)
    if encoded is None:
        return False
    return encoded == parse_ddmmyyyy(birth_date)


def gender_from_iin(iin: str) -> str | None:
    """The 7th digit of a Kazakhstan IIN encodes century-of-birth *and* gender together:
    1/3/5 = male, 2/4/6 = female (odd/even within each century pair). Used to pick the
    correct Russian verb/pronoun agreement ("не согласна" vs "не согласен") when drafting a
    first-person objection on the debtor's behalf - never guessed from the name, since
    Kazakh surname morphology is not a reliable gender signal for this purpose."""
    if not is_valid_iin_format(iin):
        return None
    century_digit = iin[6]
    if century_digit not in _CENTURY_CODE:
        return None
    return "male" if int(century_digit) % 2 == 1 else "female"

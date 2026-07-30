from __future__ import annotations

import datetime

from app.utils.validators import parse_ddmmyyyy

_GENITIVE_MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def format_date_long_ru(value: datetime.date | str) -> str:
    """'11 мая 2026 года' - the long form used inside objection/legal document body text
    (as opposed to the short 'DD.MM.YYYY' form used in signatures/footers)."""
    date_obj = parse_ddmmyyyy(value) if isinstance(value, str) else value
    month_name = _GENITIVE_MONTHS[date_obj.month - 1]
    return f"{date_obj.day} {month_name} {date_obj.year} года"


def format_date_short_ru(value: datetime.date | str) -> str:
    """'07.07.2026 г.' - used for signature-line dates."""
    date_obj = parse_ddmmyyyy(value) if isinstance(value, str) else value
    return f"{date_obj.strftime('%d.%m.%Y')} г."

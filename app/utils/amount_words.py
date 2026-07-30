from __future__ import annotations

from num2words import num2words


def amount_to_words_kzt(amount: int) -> str:
    """Render an integer KZT amount as Russian words, e.g. 120000 -> 'сто двадцать тысяч тенге'."""
    words = num2words(amount, lang="ru")
    return f"{words} тенге"


def format_amount_digits(amount: int) -> str:
    return f"{amount:,}".replace(",", " ")

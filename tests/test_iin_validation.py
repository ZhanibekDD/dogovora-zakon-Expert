from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.identity import IdentityExtraction
from app.utils.validators import (
    birth_date_from_iin,
    iin_matches_birth_date,
    is_valid_iin_format,
)


def test_valid_iin_format_accepted() -> None:
    assert is_valid_iin_format("010312500019")


@pytest.mark.parametrize("bad_iin", ["12345", "1234567890123", "abcdefghijkl", ""])
def test_invalid_iin_format_rejected(bad_iin: str) -> None:
    assert not is_valid_iin_format(bad_iin)


def test_identity_extraction_rejects_non_12_digit_iin() -> None:
    with pytest.raises(ValidationError):
        IdentityExtraction(iin="12345")


def test_identity_extraction_accepts_valid_iin() -> None:
    identity = IdentityExtraction(iin="010312500019")
    assert identity.iin == "010312500019"


def test_birth_date_derived_from_iin_matches_document() -> None:
    # Synthetic test IIN: 010312500019 encodes birth date 12.03.2001.
    encoded = birth_date_from_iin("010312500019")
    assert encoded is not None
    assert encoded.day == 12
    assert encoded.month == 3
    assert encoded.year == 2001
    assert iin_matches_birth_date("010312500019", "12.03.2001")


def test_iin_birth_date_mismatch_detected() -> None:
    assert not iin_matches_birth_date("010312500019", "01.01.1999")


def test_kazakh_characters_preserved_in_full_name() -> None:
    name = "СЕЙТЖАНОВ АЙБЕК НҰРЛАНҰЛЫ"
    identity = IdentityExtraction(full_name=name)
    assert identity.full_name == name
    for char in "ӘҚҢӨҰҮҺІ":
        assert char in identity.full_name or char not in name

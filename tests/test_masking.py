from __future__ import annotations

from app.utils.masking import mask_iin, mask_phone, mask_text


def test_mask_iin_hides_middle_digits() -> None:
    masked = mask_iin("010312500019")
    assert masked != "010312500019"
    assert masked.startswith("010312")
    assert masked.endswith("19")
    assert "****" in masked


def test_mask_iin_handles_none() -> None:
    assert mask_iin(None) == "—"


def test_mask_phone_hides_middle_digits() -> None:
    masked = mask_phone("+7 701 234 5678")
    assert masked != "+7 701 234 5678"
    assert "5678"[-2:] in masked


def test_mask_text_masks_embedded_iin_and_phone() -> None:
    text = "Клиент ИИН 010312500019, телефон +77012345678"
    masked = mask_text(text)
    assert "010312500019" not in masked
    assert "77012345678" not in masked

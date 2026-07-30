from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

from app.services.signature_asset_service import (
    SignatureAssetError,
    prepare_signature_asset,
)


def _png_with_white_margin(*, stamp: bool) -> bytes:
    size = (800, 800) if stamp else (1000, 400)
    image = Image.new("RGBA", size, "white")
    draw = ImageDraw.Draw(image)
    if stamp:
        draw.ellipse((220, 220, 580, 580), outline=(0, 65, 180, 255), width=18)
    else:
        draw.line((250, 250, 760, 140), fill=(0, 65, 180, 255), width=16)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_signature_is_cropped_and_keeps_non_square_ratio() -> None:
    prepared = prepare_signature_asset(_png_with_white_margin(stamp=False), kind="signature")
    assert prepared.width_px < 650
    assert prepared.height_px < 200
    assert prepared.width_px > prepared.height_px


def test_stamp_is_normalized_to_square_canvas() -> None:
    prepared = prepare_signature_asset(_png_with_white_margin(stamp=True), kind="stamp")
    assert prepared.width_px == prepared.height_px
    assert prepared.width_px < 500


def test_blank_png_is_rejected() -> None:
    image = Image.new("RGBA", (300, 300), (255, 255, 255, 0))
    output = io.BytesIO()
    image.save(output, format="PNG")
    with pytest.raises(SignatureAssetError):
        prepare_signature_asset(output.getvalue(), kind="stamp")

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.services.signature_asset_service import (
    SignatureAssetError,
    bind_executor_asset,
    compose_executor_mark,
    prepare_signature_asset,
    validate_executor_asset_binding,
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


def test_executor_mark_has_compact_fixed_a4_geometry() -> None:
    signature = prepare_signature_asset(_png_with_white_margin(stamp=False), kind="signature")
    stamp = prepare_signature_asset(_png_with_white_margin(stamp=True), kind="stamp")
    mark = compose_executor_mark(
        signature_png_bytes=signature.png_bytes,
        stamp_png_bytes=stamp.png_bytes,
        signer_short_name="Кияшев Ж.Д.",
        signature_width_mm=42,
        stamp_diameter_mm=28,
        block_width_mm=70,
    )

    image = Image.open(io.BytesIO(mark.png_bytes)).convert("RGBA")
    assert mark.width_mm == 70
    assert mark.height_mm == 33
    assert image.width > image.height
    assert image.getchannel("A").getbbox() is not None


def test_blank_png_is_rejected() -> None:
    image = Image.new("RGBA", (300, 300), (255, 255, 255, 0))
    output = io.BytesIO()
    image.save(output, format="PNG")
    with pytest.raises(SignatureAssetError):
        prepare_signature_asset(output.getvalue(), kind="stamp")


def test_assets_are_bound_to_current_legal_entity(tmp_path: Path) -> None:
    signature = prepare_signature_asset(_png_with_white_margin(stamp=False), kind="signature").png_bytes
    stamp = prepare_signature_asset(_png_with_white_margin(stamp=True), kind="stamp").png_bytes
    for kind, data in (("signature", signature), ("stamp", stamp)):
        bind_executor_asset(
            tmp_path,
            kind=kind,
            sha256=hashlib.sha256(data).hexdigest(),
            identifier_label="БИН",
            identifier="260740044168",
        )

    validate_executor_asset_binding(
        tmp_path,
        signature_bytes=signature,
        stamp_bytes=stamp,
        identifier_label="БИН",
        identifier="260740044168",
    )

    with pytest.raises(SignatureAssetError, match="другой организации"):
        validate_executor_asset_binding(
            tmp_path,
            signature_bytes=signature,
            stamp_bytes=stamp,
            identifier_label="ИИН",
            identifier="000725500183",
        )


def test_asset_replacement_after_binding_is_rejected(tmp_path: Path) -> None:
    signature = prepare_signature_asset(_png_with_white_margin(stamp=False), kind="signature").png_bytes
    stamp = prepare_signature_asset(_png_with_white_margin(stamp=True), kind="stamp").png_bytes
    for kind, data in (("signature", signature), ("stamp", stamp)):
        bind_executor_asset(
            tmp_path,
            kind=kind,
            sha256=hashlib.sha256(data).hexdigest(),
            identifier_label="БИН",
            identifier="260740044168",
        )

    with pytest.raises(SignatureAssetError, match="печать не подтверждена"):
        validate_executor_asset_binding(
            tmp_path,
            signature_bytes=signature,
            stamp_bytes=stamp + b"tampered",
            identifier_label="БИН",
            identifier="260740044168",
        )

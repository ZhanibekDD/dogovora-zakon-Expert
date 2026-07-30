from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError

AssetKind = Literal["signature", "stamp"]

MAX_SOURCE_SIDE_PX = 6000
MAX_OUTPUT_SIDE_PX = 1800
MIN_VISIBLE_WIDTH_PX = 24
MIN_VISIBLE_HEIGHT_PX = 12
ASSET_MANIFEST_NAME = "hashes.json"


class SignatureAssetError(ValueError):
    pass


@dataclass(frozen=True)
class PreparedSignatureAsset:
    png_bytes: bytes
    width_px: int
    height_px: int


def _legal_identity_key(identifier_label: str, identifier: str) -> str:
    return f"{identifier_label.strip().upper()}:{identifier.strip()}"


def bind_executor_asset(
    asset_dir: Path,
    *,
    kind: AssetKind,
    sha256: str,
    identifier_label: str,
    identifier: str,
) -> None:
    """Bind an uploaded image to the executor's current legal identity.

    A company transition must never silently reuse the previous entity's seal. When the
    legal identity changes, the first upload starts a fresh asset set and both files must be
    uploaded again before a final contract can be rendered.
    """

    asset_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = asset_dir / ASSET_MANIFEST_NAME
    legal_identity = _legal_identity_key(identifier_label, identifier)
    manifest: dict = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            manifest = {}

    stored_assets = manifest.get("assets")
    assets = (
        stored_assets
        if manifest.get("legal_identity") == legal_identity and isinstance(stored_assets, dict)
        else {}
    )
    assets[kind] = sha256
    payload = {
        "version": 1,
        "legal_identity": legal_identity,
        "identifier_label": identifier_label,
        "identifier": identifier,
        "assets": assets,
    }
    temporary = manifest_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(manifest_path)


def validate_executor_asset_binding(
    asset_dir: Path,
    *,
    signature_bytes: bytes,
    stamp_bytes: bytes,
    identifier_label: str,
    identifier: str,
) -> None:
    """Reject stale, replaced or legally mismatched signature/seal assets."""

    manifest_path = asset_dir / ASSET_MANIFEST_NAME
    expected_identity = _legal_identity_key(identifier_label, identifier)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        raise SignatureAssetError(
            f"подпись и печать не подтверждены для {identifier_label} {identifier}; "
            "загрузите оба PNG заново через /signature_settings"
        ) from exc

    if manifest.get("legal_identity") != expected_identity:
        raise SignatureAssetError(
            f"загруженные изображения относятся к другой организации; для "
            f"{identifier_label} {identifier} загрузите подпись и печать заново"
        )

    assets = manifest.get("assets")
    if not isinstance(assets, dict):
        raise SignatureAssetError(
            f"привязка подписи и печати повреждена; для {identifier_label} {identifier} "
            "загрузите оба PNG заново через /signature_settings"
        )
    actual = {
        "signature": hashlib.sha256(signature_bytes).hexdigest(),
        "stamp": hashlib.sha256(stamp_bytes).hexdigest(),
    }
    for kind, label in (("signature", "подпись"), ("stamp", "печать")):
        if assets.get(kind) != actual[kind]:
            raise SignatureAssetError(
                f"{label} не подтверждена для {identifier_label} {identifier}; "
                "загрузите оба PNG заново через /signature_settings"
            )


def _visible_alpha(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    source_alpha = rgba.getchannel("A")
    # Telegram/scan tools frequently turn transparency into a white canvas. Treat only
    # near-white pixels as empty; blue seal ink and dark signature strokes stay opaque.
    near_white = ImageOps.grayscale(rgba.convert("RGB")).point(lambda value: 0 if value >= 246 else 255)
    return ImageChops.multiply(source_alpha, near_white)


def prepare_signature_asset(data: bytes, *, kind: AssetKind) -> PreparedSignatureAsset:
    """Validate, crop and normalise an uploaded executor signature/seal PNG.

    The output has a tight transparent canvas and a stable aspect ratio. The DOCX renderer
    then assigns its physical millimetre size, so a 300 px and a 3000 px upload print equally.
    """

    try:
        with Image.open(io.BytesIO(data)) as opened:
            if opened.format != "PNG":
                raise SignatureAssetError("нужен PNG-файл")
            opened.load()
            if max(opened.size) > MAX_SOURCE_SIDE_PX:
                raise SignatureAssetError("изображение слишком большое (максимум 6000 px)")
            rgba = opened.convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise SignatureAssetError("PNG-файл повреждён или не читается") from exc

    alpha = _visible_alpha(rgba)
    bbox = alpha.getbbox()
    if bbox is None:
        raise SignatureAssetError("на изображении не найдено видимой подписи или печати")

    rgba.putalpha(alpha)
    cropped = rgba.crop(bbox)
    if cropped.width < MIN_VISIBLE_WIDTH_PX or cropped.height < MIN_VISIBLE_HEIGHT_PX:
        raise SignatureAssetError("изображение слишком маленькое или почти пустое")

    if max(cropped.size) > MAX_OUTPUT_SIDE_PX:
        cropped.thumbnail((MAX_OUTPUT_SIDE_PX, MAX_OUTPUT_SIDE_PX), Image.Resampling.LANCZOS)

    padding = max(4, round(max(cropped.size) * 0.025))
    if kind == "stamp":
        side = max(cropped.size) + padding * 2
        canvas = Image.new("RGBA", (side, side), (255, 255, 255, 0))
        canvas.alpha_composite(
            cropped,
            ((side - cropped.width) // 2, (side - cropped.height) // 2),
        )
    else:
        canvas = Image.new(
            "RGBA",
            (cropped.width + padding * 2, cropped.height + padding * 2),
            (255, 255, 255, 0),
        )
        canvas.alpha_composite(cropped, (padding, padding))

    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    return PreparedSignatureAsset(
        png_bytes=output.getvalue(),
        width_px=canvas.width,
        height_px=canvas.height,
    )

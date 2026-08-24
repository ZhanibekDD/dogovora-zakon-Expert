from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

AssetKind = Literal["signature", "stamp"]

MAX_SOURCE_SIDE_PX = 6000
MAX_OUTPUT_SIDE_PX = 1800
MIN_VISIBLE_WIDTH_PX = 24
MIN_VISIBLE_HEIGHT_PX = 12
ASSET_MANIFEST_NAME = "hashes.json"
MARK_DPI = 300


class SignatureAssetError(ValueError):
    pass


@dataclass(frozen=True)
class PreparedSignatureAsset:
    png_bytes: bytes
    width_px: int
    height_px: int


@dataclass(frozen=True)
class PreparedExecutorMark:
    png_bytes: bytes
    width_mm: float
    height_mm: float


def _mm_to_px(value_mm: float) -> int:
    return max(1, round(value_mm / 25.4 * MARK_DPI))


def _signer_font(size_pt: float) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    size_px = max(12, round(size_pt / 72 * MARK_DPI))
    for candidate in (
        "LiberationSerif-Regular.ttf",
        "DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size_px)
        except OSError:
            continue
    return ImageFont.load_default()


def _resize_to_width(image: Image.Image, width_px: int, *, max_height_px: int) -> Image.Image:
    ratio = min(width_px / image.width, max_height_px / image.height)
    size = (
        max(1, round(image.width * ratio)),
        max(1, round(image.height * ratio)),
    )
    return image.resize(size, Image.Resampling.LANCZOS)


def _set_opacity(image: Image.Image, opacity: float) -> Image.Image:
    image = image.copy()
    alpha = image.getchannel("A")
    image.putalpha(alpha.point(lambda value: round(value * opacity)))
    return image


def compose_executor_mark(
    *,
    signature_png_bytes: bytes,
    stamp_png_bytes: bytes,
    signer_short_name: str,
    signature_width_mm: float,
    stamp_diameter_mm: float,
    block_width_mm: float,
) -> PreparedExecutorMark:
    """Build a compact paper-like signature/seal composition for the executor.

    The goal is restrained realism: the handwritten signature lightly crosses the signing
    line, the seal is smaller and slightly rotated with reduced opacity, and the printed
    signer name stays visually separate below. The whole mark is composed at 300 DPI and
    inserted into Word as one transparent image so Word/LibreOffice cannot rearrange it.
    """

    block_height_mm = 33.0
    width_px = _mm_to_px(block_width_mm)
    height_px = _mm_to_px(block_height_mm)
    canvas = Image.new("RGBA", (width_px, height_px), (255, 255, 255, 0))

    signature = Image.open(io.BytesIO(signature_png_bytes)).convert("RGBA")
    stamp = Image.open(io.BytesIO(stamp_png_bytes)).convert("RGBA")

    signature = _resize_to_width(
        signature,
        _mm_to_px(signature_width_mm),
        max_height_px=_mm_to_px(15.8),
    ).rotate(-0.7, resample=Image.Resampling.BICUBIC, expand=True)

    stamp_side = _mm_to_px(stamp_diameter_mm)
    stamp = stamp.resize((stamp_side, stamp_side), Image.Resampling.LANCZOS)
    stamp = _set_opacity(stamp, 0.84).rotate(
        -1.5,
        resample=Image.Resampling.BICUBIC,
        expand=True,
    )

    draw = ImageDraw.Draw(canvas)
    baseline_y = _mm_to_px(20.5)
    line_start_x = _mm_to_px(2.3)
    line_end_x = _mm_to_px(29.0)
    line_width = max(2, _mm_to_px(0.18))
    draw.line(
        (line_start_x, baseline_y, line_end_x, baseline_y),
        fill=(80, 80, 80, 210),
        width=line_width,
    )

    # A slight crossing of the line is enough to look hand-signed without obscuring the seal.
    signature_x = _mm_to_px(1.0)
    signature_y = baseline_y + _mm_to_px(1.0) - signature.height
    canvas.alpha_composite(signature, (signature_x, max(0, signature_y)))

    # Keep the seal compact and slightly over the right tail of the signature.
    stamp_x = min(width_px - stamp.width, _mm_to_px(29.2))
    stamp_y = _mm_to_px(0.6)
    canvas.alpha_composite(stamp, (max(0, stamp_x), stamp_y))

    draw.text(
        (_mm_to_px(2.5), _mm_to_px(30.6)),
        f"/ {signer_short_name} /",
        font=_signer_font(8.2),
        fill=(45, 45, 45, 255),
        anchor="ls",
    )

    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=True, dpi=(MARK_DPI, MARK_DPI))
    return PreparedExecutorMark(
        png_bytes=output.getvalue(),
        width_mm=block_width_mm,
        height_mm=block_height_mm,
    )


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
    near_white = ImageOps.grayscale(rgba.convert("RGB")).point(
        lambda value: 0 if value >= 246 else 255
    )
    return ImageChops.multiply(source_alpha, near_white)


def prepare_signature_asset(data: bytes, *, kind: AssetKind) -> PreparedSignatureAsset:
    """Validate, crop and normalise an uploaded executor signature/seal PNG."""

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

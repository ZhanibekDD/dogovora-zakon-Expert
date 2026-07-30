from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

CONVERT_TIMEOUT_SECONDS = 90

_CYRILLIC_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/timesbd.ttf",
]
_registered_font_name: str | None = None


def _cyrillic_font_name() -> str:
    """Register a TTF that actually has Cyrillic glyphs so the watermark and signature
    date stamp render correctly instead of as boxes: reportlab's built-in Helvetica/Times
    fonts only cover Latin-1 and silently draw '?????' for Кириллица text."""
    global _registered_font_name
    if _registered_font_name is not None:
        return _registered_font_name

    for candidate in _CYRILLIC_FONT_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            pdfmetrics.registerFont(TTFont("ZakonExpertCyrillic", str(path)))
            _registered_font_name = "ZakonExpertCyrillic"
            return _registered_font_name

    logger.warning("no_cyrillic_font_found_falling_back_to_helvetica")
    _registered_font_name = "Helvetica-Bold"
    return _registered_font_name


class PdfConversionError(Exception):
    pass


def convert_docx_to_pdf(input_path: Path, output_path: Path) -> Path:
    """Convert a DOCX file to PDF via headless LibreOffice.

    Runs the conversion in an isolated temporary directory so concurrent jobs never race on
    each other's output files, enforces a hard timeout so a hung soffice process cannot stall
    the worker forever, and verifies both the process return code and the resulting file's
    existence before declaring success.
    """
    settings = get_settings()
    if not input_path.exists():
        raise PdfConversionError("Исходный DOCX-файл не найден")
    if output_path.exists():
        raise PdfConversionError("Файл назначения уже существует, конвертация отменена")

    with tempfile.TemporaryDirectory(prefix="zakonexpert_pdf_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        try:
            result = subprocess.run(
                [
                    settings.libreoffice_path,
                    "--headless",
                    "--norestore",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(tmp_path),
                    str(input_path),
                ],
                capture_output=True,
                timeout=CONVERT_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            logger.error("pdf_conversion_timeout", timeout=CONVERT_TIMEOUT_SECONDS)
            raise PdfConversionError("Конвертация в PDF превысила лимит времени") from exc
        except FileNotFoundError as exc:
            logger.error("pdf_conversion_libreoffice_missing")
            raise PdfConversionError("LibreOffice (soffice) не найден в системе") from exc

        if result.returncode != 0:
            logger.error("pdf_conversion_failed", returncode=result.returncode)
            raise PdfConversionError("LibreOffice завершился с ошибкой при конвертации")

        produced = tmp_path / f"{input_path.stem}.pdf"
        if not produced.exists():
            logger.error("pdf_conversion_no_output")
            raise PdfConversionError("PDF-файл не был создан")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(produced), str(output_path))

    return output_path


def overlay_client_signature(
    *,
    input_pdf_path: Path,
    output_pdf_path: Path,
    signature_png_bytes: bytes,
    signed_at_text: str,
    page_index: int = -1,
) -> Path:
    """Composite the client's own hand-drawn signature image onto the approved PDF's
    signature area. Only ever called from signing_service after the client has completed
    the consent + canvas-drawing flow themselves - never from any bot/admin code path."""
    reader = PdfReader(str(input_pdf_path))
    writer = PdfWriter()
    target_index = page_index if page_index >= 0 else len(reader.pages) - 1

    for idx, page in enumerate(reader.pages):
        if idx == target_index:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            buffer = io.BytesIO()
            c = canvas.Canvas(buffer, pagesize=(width, height))
            img_reader = _image_reader(signature_png_bytes)
            sig_width, sig_height = 160, 60
            x = width / 2 + 10
            y = 90
            c.drawImage(
                img_reader, x, y, width=sig_width, height=sig_height,
                preserveAspectRatio=True, mask="auto",
            )
            c.setFont(_cyrillic_font_name(), 9)
            c.drawString(x, y - 14, f"Подписано электронно: {signed_at_text}")
            c.save()
            buffer.seek(0)
            overlay = PdfReader(buffer)
            page.merge_page(overlay.pages[0])
        writer.add_page(page)

    output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_pdf_path, "wb") as fh:
        writer.write(fh)
    return output_pdf_path


def _image_reader(png_bytes: bytes):
    from reportlab.lib.utils import ImageReader

    return ImageReader(io.BytesIO(png_bytes))


def generate_uuid_filename(suffix: str) -> str:
    return f"{uuid.uuid4()}{suffix}"


def rasterize_pdf_pages(pdf_bytes: bytes, *, max_pages: int = 2, dpi: int = 200) -> list[bytes]:
    """Rasterize the first `max_pages` pages of an uploaded ID-document PDF to PNG bytes so
    they can be sent to the OpenAI vision extraction alongside (or instead of) a photo.
    Kazakhstan ID cards are sometimes submitted as a two-page PDF (front page + back page);
    both are rasterized so the model can read whichever side actually carries the ИИН/ФИО.
    """
    import fitz  # PyMuPDF - self-contained, no system Poppler dependency

    images: list[bytes] = []
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        for page_index in range(min(max_pages, document.page_count)):
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(matrix=matrix)
            images.append(pixmap.tobytes("png"))
    return images

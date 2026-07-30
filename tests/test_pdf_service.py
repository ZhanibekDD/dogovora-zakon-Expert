from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from app.services import pdf_service

SOFFICE_AVAILABLE = shutil.which("soffice") is not None or shutil.which("soffice.exe") is not None


def _make_simple_pdf(path: Path, text: str = "Sample contract page") -> Path:
    c = canvas.Canvas(str(path), pagesize=(595, 842))
    c.drawString(72, 800, text)
    c.save()
    return path


def test_final_pdf_has_no_watermark(tmp_path: Path) -> None:
    """There is no separate draft/watermark stage: contracts are converted straight from the
    final DOCX (signature/stamp embedded), so the PDF must never contain a draft marker."""
    final_pdf = _make_simple_pdf(tmp_path / "final.pdf", text="Final signed contract text")
    reader = PdfReader(str(final_pdf))
    text = reader.pages[0].extract_text() or ""
    assert "ЧЕРНОВИК" not in text


def test_overlay_client_signature_produces_new_file(tmp_path: Path) -> None:
    from PIL import Image

    source = _make_simple_pdf(tmp_path / "approved.pdf")
    output = tmp_path / "signed.pdf"

    sig_path = tmp_path / "sig.png"
    Image.new("RGBA", (200, 80), (0, 0, 0, 0)).save(sig_path)
    sig_bytes = sig_path.read_bytes()

    pdf_service.overlay_client_signature(
        input_pdf_path=source,
        output_pdf_path=output,
        signature_png_bytes=sig_bytes,
        signed_at_text="13.07.2026 12:00",
    )
    assert output.exists()
    assert output.stat().st_size > 0


@pytest.mark.skipif(not SOFFICE_AVAILABLE, reason="LibreOffice (soffice) is not installed on this machine")
def test_convert_docx_to_pdf_real_libreoffice(tmp_path: Path) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    docx_path = settings.templates_dir / "master_v1.docx"
    output_path = tmp_path / "converted.pdf"

    pdf_service.convert_docx_to_pdf(docx_path, output_path)
    assert output_path.exists()


def test_convert_docx_to_pdf_refuses_to_overwrite_existing_output(tmp_path: Path) -> None:
    docx_path = tmp_path / "input.docx"
    docx_path.write_bytes(b"not a real docx, existence check only")
    existing_output = tmp_path / "output.pdf"
    existing_output.write_text("already here")

    with pytest.raises(pdf_service.PdfConversionError):
        pdf_service.convert_docx_to_pdf(docx_path, existing_output)


def test_convert_docx_to_pdf_missing_input_raises(tmp_path: Path) -> None:
    with pytest.raises(pdf_service.PdfConversionError):
        pdf_service.convert_docx_to_pdf(tmp_path / "missing.docx", tmp_path / "out.pdf")

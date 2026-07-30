from __future__ import annotations

from docx import Document as DocxReader
from docx.shared import Mm

from app.core.config import get_settings


def _load_master_template():
    settings = get_settings()
    return DocxReader(str(settings.templates_dir / "master_v1.docx"))


def _table_text(table) -> str:
    chunks: list[str] = []
    for row in table.rows:
        for cell in row.cells:
            chunks.append(cell.text)
            chunks.extend(_table_text(nested) for nested in cell.tables)
    return "\n".join(chunks)


def test_page_is_a4_with_adequate_margins() -> None:
    doc = _load_master_template()
    section = doc.sections[0]
    assert abs(section.page_width - Mm(210)) < Mm(1)
    assert abs(section.page_height - Mm(297)) < Mm(1)
    # allow ~0.1mm of EMU rounding slack introduced by python-docx's Mm() conversion
    tolerance = Mm(0.2)
    assert section.top_margin + tolerance >= Mm(15)
    assert section.bottom_margin + tolerance >= Mm(15)
    assert section.left_margin + tolerance >= Mm(15)
    assert section.right_margin + tolerance >= Mm(15)


def test_body_font_is_times_new_roman_11_or_12pt() -> None:
    doc = _load_master_template()
    normal_style = doc.styles["Normal"]
    assert normal_style.font.name == "Times New Roman"
    assert normal_style.font.size.pt in (11, 12)


def test_signature_area_table_present_with_two_columns() -> None:
    doc = _load_master_template()
    assert len(doc.tables) >= 2  # requisites table + signature table
    signature_table = doc.tables[-1]
    assert len(signature_table.columns) == 2


def test_signature_placeholders_present_in_template() -> None:
    doc = _load_master_template()
    full_text = "\n".join(_table_text(table) for table in doc.tables)
    assert "{{ executor_signature }}" in full_text
    assert "{{ executor_stamp }}" in full_text
    assert "{{ client_signature }}" in full_text
    assert "{{ client_signature_date }}" in full_text


def test_required_placeholders_present() -> None:
    doc = _load_master_template()
    all_text = "\n".join(p.text for p in doc.paragraphs)
    all_text += "\n".join(_table_text(table) for table in doc.tables)
    required = [
        "{{ contract_number }}",
        "{{ contract_date }}",
        "{{ contract_city }}",
        "{{ client_full_name }}",
        "{{ client_iin }}",
        "{{ client_phone }}",
        "{{ service_subject }}",
        "{{ result_definition }}",
        "{{ amount_digits }}",
        "{{ amount_words }}",
        "{{ payment_terms }}",
        "{{ penalty_clause }}",
    ]
    for placeholder in required:
        assert placeholder in all_text, f"missing {placeholder}"

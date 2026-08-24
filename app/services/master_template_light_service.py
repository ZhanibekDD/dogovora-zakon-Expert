from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import RGBColor

from app.services.master_template_service import build_master_template as build_v3_template

SCHEMA_MARKER = "ZakonExpert contract schema v4 light-trust"
NAVY = "20364F"
GOLD = "B78A43"
PALE_BLUE = "F3F6F9"
PALE_GOLD = "FBF8F1"
WHITE = "FFFFFF"
DARK_FILLS = {"102A43", "173A5E", "171717", "20242A", "000000"}


def _cell_fill(cell) -> str | None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.first_child_found_in("w:shd")
    return shd.get(qn("w:fill")) if shd is not None else None


def _set_cell_fill(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.first_child_found_in("w:shd")
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def _set_cell_text_color(cell, color: str) -> None:
    rgb = RGBColor.from_string(color)
    for paragraph in cell.paragraphs:
        for run in paragraph.runs:
            run.font.color.rgb = rgb


def _set_cell_text(cell, text: str, *, bold: bool = False, color: str = NAVY) -> None:
    paragraph = cell.paragraphs[0]
    for run in paragraph.runs:
        run.text = ""
    if not paragraph.runs:
        run = paragraph.add_run(text)
    else:
        run = paragraph.runs[0]
        run.text = text
    run.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)


def _all_paragraphs(doc):
    yield from doc.paragraphs
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs
    for section in doc.sections:
        yield from section.header.paragraphs
        yield from section.footer.paragraphs
        for part in (section.header, section.footer):
            for table in part.tables:
                for row in table.rows:
                    for cell in row.cells:
                        yield from cell.paragraphs


def _lighten_tables(doc) -> None:
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                fill = (_cell_fill(cell) or "").upper()
                if fill in DARK_FILLS:
                    _set_cell_fill(cell, PALE_BLUE)
                    _set_cell_text_color(cell, NAVY)


def _replace_text(doc, old: str, new: str) -> None:
    for paragraph in _all_paragraphs(doc):
        if old in paragraph.text:
            for run in paragraph.runs:
                run.text = run.text.replace(old, new)


def _rewrite_payment_table(doc) -> None:
    target = None
    for table in doc.tables:
        text = "\n".join(cell.text for row in table.rows for cell in row.cells)
        if "{{ executor_bank_beneficiary }}" in text or "{{ executor_bank_iban }}" in text:
            target = table
            break
    if target is None:
        return

    rows = [
        (
            "ОСНОВНОЙ СПОСОБ",
            "Оплата по счёту или платёжной ссылке, выставленной ZakonExpert для конкретного договора.",
        ),
        (
            "ИДЕНТИФИКАЦИЯ",
            "В назначении платежа или платёжном документе должны быть указаны номер договора и сумма.",
        ),
        (
            "ПОДТВЕРЖДЕНИЕ",
            "Факт оплаты подтверждается банковским, кассовым либо иным платёжным документом, позволяющим установить получателя, плательщика, сумму и дату.",
        ),
        (
            "КОНТАКТ",
            "Для получения счёта и подтверждения оплаты: {{ executor_phone }} · {{ executor_website }}.",
        ),
    ]
    for row, (label, value) in zip(target.rows, rows, strict=False):
        cells = row.cells
        value_cell = cells[1].merge(cells[3]) if len(cells) >= 4 else cells[-1]
        _set_cell_fill(cells[0], PALE_GOLD)
        _set_cell_text(cells[0], label, bold=True, color=GOLD)
        _set_cell_text(value_cell, value, color=NAVY)
        for extra in cells[2:]:
            if extra is not value_cell:
                _set_cell_fill(extra, WHITE)


def _rewrite_security_notice(doc) -> None:
    for table in doc.tables:
        text = "\n".join(cell.text for row in table.rows for cell in row.cells)
        if "БЕЗОПАСНОСТЬ ОПЛАТЫ" not in text:
            continue
        for row in table.rows:
            for cell in row.cells:
                if "БЕЗОПАСНОСТЬ ОПЛАТЫ" in cell.text:
                    _set_cell_fill(cell, PALE_GOLD)
                    _set_cell_text(
                        cell,
                        "БЕЗОПАСНОСТЬ ОПЛАТЫ: оплачивайте только по счёту или платёжной ссылке, полученной от ZakonExpert по этому договору. Не переводите деньги по реквизитам, которых нет в счёте или подтверждённой платёжной ссылке. ZakonExpert не запрашивает SMS-коды, пароли и доступ к банковскому приложению.",
                        color=NAVY,
                    )
                    return


def build_master_template(output_path: Path) -> Path:
    output_path = Path(output_path)
    build_v3_template(output_path)
    doc = Document(str(output_path))
    doc.core_properties.subject = SCHEMA_MARKER
    doc.core_properties.title = "Договор оказания услуг ZakonExpert — light trust"

    _lighten_tables(doc)
    _replace_text(doc, "ПЛАТЁЖНЫЕ РЕКВИЗИТЫ · сверяйте перед оплатой", "ПОРЯДОК ОПЛАТЫ · сверяйте перед оплатой")
    _replace_text(doc, "ПЛАТЁЖНЫЕ РЕКВИЗИТЫ", "ПОРЯДОК ОПЛАТЫ")
    _replace_text(
        doc,
        "{{ executor_payment_details }}",
        "по счёту или платёжной ссылке, письменно подтверждённой Исполнителем",
    )
    _rewrite_payment_table(doc)
    _rewrite_security_notice(doc)

    doc.save(str(output_path))
    return output_path


def ensure_master_template(output_path: Path) -> Path:
    output_path = Path(output_path)
    if output_path.exists():
        try:
            current = Document(str(output_path))
            if current.core_properties.subject == SCHEMA_MARKER:
                return output_path
        except (OSError, ValueError, KeyError):
            pass
    return build_master_template(output_path)

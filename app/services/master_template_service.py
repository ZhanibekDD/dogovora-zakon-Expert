from __future__ import annotations

import io
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor, Twips
from PIL import Image, ImageDraw, ImageFont

SCHEMA_MARKER = "ZakonExpert contract schema v2"
FONT = "Times New Roman"
UI_FONT = "Arial"
INK = "171717"
GOLD = "B58A3A"
MUTED = "667085"
PALE = "F7F8FA"
PALE_GOLD = "FBF7EE"
BORDER = "CDD4DC"
WHITE = "FFFFFF"
PAGE_W_MM = 210
PAGE_H_MM = 297
MARGIN_LR_MM = 16
MARGIN_TB_MM = 15
CONTENT_W_MM = PAGE_W_MM - MARGIN_LR_MM * 2


def _font(run, *, size=9.5, bold=False, italic=False, color=INK, family=FONT) -> None:
    run.font.name = family
    rfonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    for key in ("w:ascii", "w:hAnsi", "w:eastAsia"):
        rfonts.set(qn(key), family)
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def _shade(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.first_child_found_in("w:shd")
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def _cell_margins(cell, *, top=70, start=105, bottom=70, end=105) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for edge, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        el = tc_mar.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            tc_mar.append(el)
        el.set(qn("w:w"), str(value))
        el.set(qn("w:type"), "dxa")


def _table(table, widths_mm: list[float], *, border=BORDER, size=5) -> None:
    widths = [round(width / 25.4 * 1440) for width in widths_mm]
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.first_child_found_in("w:tblW")
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(sum(widths)))
    tbl_w.set(qn("w:type"), "dxa")
    layout = tbl_pr.first_child_found_in("w:tblLayout")
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        tbl_pr.append(layout)
    layout.set(qn("w:type"), "fixed")
    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)
    borders = tbl_pr.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            borders.append(el)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:color"), border)
        el.set(qn("w:space"), "0")
    for row in table.rows:
        for idx, cell in enumerate(row.cells):
            width = widths[min(idx, len(widths) - 1)]
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.first_child_found_in("w:tcW")
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(width))
            tc_w.set(qn("w:type"), "dxa")
            cell.width = Twips(width)
            _cell_margins(cell)


def _no_borders(table) -> None:
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            borders.append(el)
        el.set(qn("w:val"), "nil")


def _keep(row) -> None:
    for cell in row.cells:
        for paragraph in cell.paragraphs:
            paragraph.paragraph_format.keep_together = True


def _part(doc, roman: str, title: str) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(3)
    _font(p.add_run(f"ЧАСТЬ {roman} · {title}"), size=8.5, bold=True, color=GOLD, family=UI_FONT)


def _section(doc, number: str, title: str) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    _font(p.add_run(f"{number}. {title}"), size=10.2, bold=True, family=UI_FONT)


def _clause(doc, number: str, text: str) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.first_line_indent = Mm(5.5)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(2.1)
    p.paragraph_format.line_spacing = 1.02
    _font(p.add_run(number + " "), size=9.25, bold=True)
    _font(p.add_run(text), size=9.25)


def _brand_mark() -> io.BytesIO:
    size = 420
    image = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    ink = (23, 23, 23, 255)
    gold = (181, 138, 58, 255)
    draw.ellipse((18, 18, size - 18, size - 18), outline=ink, width=14)
    draw.ellipse((38, 38, size - 38, size - 38), outline=gold, width=5)
    draw.polygon([(130, 110), (210, 78), (290, 110), (276, 250), (210, 320), (144, 250)], fill=ink)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", 68)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "ZE", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) / 2, 194 - th / 2), "ZE", font=font, fill=(255, 255, 255, 255))
    draw.line((112, 350, 308, 350), fill=gold, width=5)
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    out.seek(0)
    return out


def _set_defaults(doc) -> None:
    section = doc.sections[0]
    section.page_width = Mm(PAGE_W_MM)
    section.page_height = Mm(PAGE_H_MM)
    section.left_margin = Mm(MARGIN_LR_MM)
    section.right_margin = Mm(MARGIN_LR_MM)
    section.top_margin = Mm(MARGIN_TB_MM)
    section.bottom_margin = Mm(MARGIN_TB_MM)
    section.header_distance = Mm(6)
    section.footer_distance = Mm(7)
    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(11)
    normal._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT)
    normal.paragraph_format.space_after = Pt(2)
    normal.paragraph_format.line_spacing = 1.02


def _header_footer(doc) -> None:
    section = doc.sections[0]
    hp = section.header.paragraphs[0]
    hp.clear()
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _font(hp.add_run("ZAKONEXPERT  ·  ДОГОВОР № {{ contract_number }}"), size=7.6, bold=True, color=MUTED, family=UI_FONT)
    fp = section.footer.paragraphs[0]
    fp.clear()
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _font(fp.add_run("ТОО «ZakonExpert»  ·  {{ executor_phone }}  ·  {{ executor_website }}"), size=7.2, color=MUTED, family=UI_FONT)


def _title_page(doc) -> None:
    hero = doc.add_table(rows=1, cols=2)
    _table(hero, [34, CONTENT_W_MM - 34], border=WHITE, size=0)
    _no_borders(hero)
    logo_cell, text_cell = hero.rows[0].cells
    logo_cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    logo_cell.paragraphs[0].add_run().add_picture(_brand_mark(), width=Mm(22))
    p = text_cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    _font(p.add_run("ZAKONEXPERT\n"), size=13.5, bold=True, family=UI_FONT)
    _font(p.add_run("ЮРИДИЧЕСКОЕ СОПРОВОЖДЕНИЕ · ДОКУМЕНТЫ · РЕЗУЛЬТАТ"), size=7.2, bold=True, color=GOLD, family=UI_FONT)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(1)
    _font(p.add_run("ДОГОВОР ОКАЗАНИЯ УСЛУГ"), size=15, bold=True, family=UI_FONT)
    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p2.paragraph_format.space_after = Pt(4)
    _font(p2.add_run("№ {{ contract_number }}"), size=10.5, bold=True, color=GOLD, family=UI_FONT)
    meta = doc.add_table(rows=1, cols=2)
    _table(meta, [CONTENT_W_MM / 2, CONTENT_W_MM / 2], border=WHITE, size=0)
    _no_borders(meta)
    _font(meta.cell(0, 0).paragraphs[0].add_run("{{ contract_city }}"), size=8.6, bold=True)
    meta.cell(0, 1).paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _font(meta.cell(0, 1).paragraphs[0].add_run("{{ contract_date }} г."), size=8.6, bold=True)


def _page1(doc) -> None:
    _title_page(doc)
    intro = doc.add_paragraph()
    intro.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    intro.paragraph_format.space_after = Pt(4)
    _font(intro.add_run("{{ executor_full_name }}, {{ executor_identifier_label }} {{ executor_identifier }}, в лице руководителя {{ executor_director_name }}, действующего на основании Устава, именуемое «Исполнитель», и {{ client_full_name }}, ИИН {{ client_iin }}, именуемый(ая) «Клиент», совместно — «Стороны», заключили настоящий договор."), size=9.0)
    _part(doc, "I", "ИНДИВИДУАЛЬНЫЕ УСЛОВИЯ")
    summary = doc.add_table(rows=4, cols=2)
    _table(summary, [39, CONTENT_W_MM - 39])
    rows = [
        ("ЧТО ДЕЛАЕМ", "{{ service_subject }}"),
        ("ПРОВЕРЯЕМЫЙ РЕЗУЛЬТАТ", "{{ result_definition }}"),
        ("СРОК НАШИХ ДЕЙСТВИЙ", "{{ work_period }}"),
        ("СТОИМОСТЬ / ОПЛАТА", "{{ amount_digits }} ({{ amount_words }}). {{ payment_terms }}"),
    ]
    for row, (label, value) in zip(summary.rows, rows, strict=True):
        _shade(row.cells[0], PALE_GOLD)
        _font(row.cells[0].paragraphs[0].add_run(label), size=7.6, bold=True, color=GOLD, family=UI_FONT)
        _font(row.cells[1].paragraphs[0].add_run(value), size=8.5, bold=label.startswith("СТОИМОСТЬ"))
        _keep(row)
    _section(doc, "1", "ПРЕДМЕТ И РЕЗУЛЬТАТ")
    _clause(doc, "1.1.", "{{ service_subject }}")
    _clause(doc, "1.2.", "В состав услуг входят: {{ service_actions }}.")
    _clause(doc, "1.3.", "Проверяемый результат оказания услуг: {{ result_definition }}. Исполнитель подтверждает выполненные действия документами, талонами, ответами органов, перепиской либо иными объективными материалами.")
    _section(doc, "2", "ПОРЯДОК И СРОКИ")
    _clause(doc, "2.1.", "Исполнитель начинает работу после получения необходимых документов и сведений Клиента, а при предоплате — после её поступления.")
    _clause(doc, "2.2.", "Срок действий Исполнителя: {{ work_period }}. Время рассмотрения обращений судом, ЧСИ, нотариусом, банком, взыскателем и государственными органами не включается в этот срок; Исполнитель информирует Клиента о таких периодах ожидания.")
    _clause(doc, "2.3.", "Клиент своевременно передаёт уведомления, постановления, судебные извещения и другие материалы по делу. Задержка предоставления необходимых данных соразмерно продлевает срок работы.")
    _section(doc, "3", "СТОИМОСТЬ И ОПЛАТА")
    _clause(doc, "3.1.", "Стоимость услуг составляет {{ amount_digits }} ({{ amount_words }}). Увеличение согласованной стоимости без письменного согласия Клиента не допускается.")
    _clause(doc, "3.2.", "{{ payment_terms }}")
    _clause(doc, "3.3.", "Оплата производится {{ executor_payment_details }}. Факт оплаты подтверждается банковским чеком, квитанцией либо иным платёжным документом.")
    _clause(doc, "3.4.", "{{ penalty_clause }}")


def _page2(doc) -> None:
    doc.add_page_break()
    _part(doc, "II", "ПРАВИЛА РАБОТЫ И ГАРАНТИИ")
    _section(doc, "4", "ОБЯЗАННОСТИ ИСПОЛНИТЕЛЯ")
    _clause(doc, "4.1.", "Исполнитель обязуется добросовестно анализировать материалы, готовить согласованные документы, соблюдать применимые сроки своих действий и информировать Клиента о существенных этапах.")
    _clause(doc, "4.2.", "По запросу Клиента Исполнитель предоставляет копии подготовленных и направленных документов, полученных ответов и подтверждений подачи.")
    _clause(doc, "4.3.", "Исполнитель выбирает законные способы сопровождения в пределах предмета договора и вправе запросить дополнительные сведения, необходимые для качественного выполнения поручения.")
    _clause(doc, "4.4.", "Решение суда, ЧСИ, нотариуса, банка, взыскателя или государственного органа принимается соответствующим лицом самостоятельно. Исполнитель отвечает за качество и своевременность собственных действий в согласованном объёме.")
    _section(doc, "5", "ОБЯЗАННОСТИ КЛИЕНТА И ПРИЁМКА")
    _clause(doc, "5.1.", "Клиент предоставляет полные и достоверные сведения, сообщает о платежах, соглашениях, судебных актах и иных обстоятельствах, влияющих на дело, и своевременно подписывает документы, когда требуется его личная подпись или ЭЦП.")
    _clause(doc, "5.2.", "Исполнитель направляет Клиенту результат и подтверждающие материалы. Клиент вправе в течение 5 рабочих дней направить конкретные мотивированные замечания. При их отсутствии соответствующий объём услуг считается принятым.")
    _clause(doc, "5.3.", "Подтверждённые недостатки подготовленных Исполнителем документов устраняются без дополнительной оплаты в разумный срок.")
    _section(doc, "6", "ПРЕКРАЩЕНИЕ, РАСХОДЫ И ОТВЕТСТВЕННОСТЬ")
    _clause(doc, "6.1.", "Клиент вправе отказаться от договора. Стороны производят расчёт исходя из фактически выполненных согласованных действий и документально подтверждённых расходов; неиспользованный остаток оплаты возвращается после сверки.")
    _clause(doc, "6.2.", "Обязательные платежи третьим лицам — государственная пошлина, нотариальные, почтовые и иные согласованные расходы — оплачиваются отдельно только после предварительного уведомления Клиента, если иное прямо не включено в стоимость.")
    _clause(doc, "6.3.", "Исполнитель вправе приостановить работу, если без документов или действий Клиента продолжение объективно невозможно, предварительно сообщив, что требуется и как это влияет на срок.")
    _clause(doc, "6.4.", "Исполнитель вправе прекратить договор при требовании незаконных действий, заведомо недостоверных сведениях или существенном повторном нарушении обязанностей Клиентом после письменного предупреждения и предоставления разумного срока для устранения нарушения.")
    _section(doc, "7", "ПЕРСОНАЛЬНЫЕ ДАННЫЕ И ЭЛЕКТРОННОЕ ВЗАИМОДЕЙСТВИЕ")
    _clause(doc, "7.1.", "Клиент даёт согласие на сбор, обработку и хранение персональных данных в объёме, необходимом для исполнения договора, подготовки и направления документов, связи и хранения доказательств выполненной работы.")
    _clause(doc, "7.2.", "Исполнитель принимает разумные меры защиты персональных данных и не передаёт их третьим лицам, кроме случаев, необходимых для исполнения поручения или предусмотренных законом.")
    _clause(doc, "7.3.", "Переписка, скан-копии и сообщения, позволяющие определить отправителя, содержание и дату, могут использоваться как доказательство согласований и уведомлений. Документ с ЭЦП применяется в случаях, установленных законодательством Республики Казахстан.")
    _section(doc, "8", "ЗАКЛЮЧИТЕЛЬНЫЕ ПОЛОЖЕНИЯ")
    _clause(doc, "8.1.", "Договор вступает в силу с даты подписания на бумаге, ЭЦП либо простой электронной подписью через персональную страницу ZakonExpert с явным подтверждением согласия и действует до полного исполнения обязательств.")
    _clause(doc, "8.2.", "Изменения действительны при письменном согласовании, включая электронную переписку, позволяющую определить Стороны и содержание изменения.")
    _clause(doc, "8.3.", "Недействительность одного положения не влечёт недействительность остальных положений договора. Каждая Сторона вправе сохранить и получить свою копию договора.")


def _lines(cell, items: list[tuple[str, bool]]) -> None:
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.0
    for idx, (text, bold) in enumerate(items):
        if idx:
            p.add_run("\n")
        _font(p.add_run(text), size=8.25, bold=bold)


def _page3(doc) -> None:
    doc.add_page_break()
    _part(doc, "III", "РЕКВИЗИТЫ И ПОДПИСИ")
    _section(doc, "9", "РЕКВИЗИТЫ, ОПЛАТА И ПОДПИСИ")
    parties = doc.add_table(rows=2, cols=2)
    _table(parties, [CONTENT_W_MM / 2, CONTENT_W_MM / 2])
    for cell, text in zip(parties.rows[0].cells, ("ИСПОЛНИТЕЛЬ", "КЛИЕНТ"), strict=True):
        _shade(cell, INK)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        _font(cell.paragraphs[0].add_run(text), size=8.4, bold=True, color=WHITE, family=UI_FONT)
    _lines(parties.rows[1].cells[0], [
        ("{{ executor_brand_name }}", True),
        ("{{ executor_full_name }}", False),
        ("{{ executor_identifier_label }}: {{ executor_identifier }}", False),
        ("Руководитель: {{ executor_director_name }}", False),
        ("Юридический адрес: {{ executor_address }}", False),
        ("Тел./WhatsApp: {{ executor_phone }}", False),
        ("Сайт: {{ executor_website }}", False),
    ])
    _lines(parties.rows[1].cells[1], [
        ("{{ client_full_name }}", True),
        ("ИИН: {{ client_iin }}", False),
        ("Тел./WhatsApp: {{ client_phone }}", False),
        ("Адрес: {{ client_address }}", False),
    ])
    for cell in parties.rows[1].cells:
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
        _cell_margins(cell, top=95, start=125, bottom=95, end=125)
    _keep(parties.rows[1])

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(2)
    _font(p.add_run("ПЛАТЁЖНЫЕ РЕКВИЗИТЫ"), size=8.8, bold=True, family=UI_FONT)
    payments = doc.add_table(rows=4, cols=4)
    _table(payments, [33, 56, 32, CONTENT_W_MM - 121])
    rows = [
        ("Получатель", "{{ executor_bank_beneficiary }}", "Банк", "{{ executor_bank_name }}"),
        ("ИИН/БИН получателя", "{{ executor_bank_beneficiary_identifier }}", "БИК / SWIFT", "{{ executor_bank_bic }}"),
        ("IBAN KZT", "{{ executor_bank_iban }}", "Назначение", "{{ executor_bank_payment_purpose }}"),
        ("Kaspi", "{{ executor_kaspi_number }}", "Получатель Kaspi", "{{ executor_kaspi_receiver }}"),
    ]
    for row, values in zip(payments.rows, rows, strict=True):
        for idx, value in enumerate(values):
            if idx in (0, 2):
                _shade(row.cells[idx], PALE_GOLD)
            _font(row.cells[idx].paragraphs[0].add_run(value), size=7.5 if idx in (0, 2) else 7.9, bold=idx in (0, 2), color=GOLD if idx in (0, 2) else INK, family=UI_FONT if idx in (0, 2) else FONT)
            row.cells[idx].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        _keep(row)

    safe = doc.add_table(rows=1, cols=1)
    _table(safe, [CONTENT_W_MM], border=GOLD, size=7)
    _shade(safe.cell(0, 0), PALE_GOLD)
    sp = safe.cell(0, 0).paragraphs[0]
    _font(sp.add_run("БЕЗОПАСНОСТЬ ОПЛАТЫ: "), size=7.6, bold=True, color=GOLD, family=UI_FONT)
    _font(sp.add_run("сверьте получателя, ИИН/БИН, сумму и назначение с этим разделом и сохраните чек. Получатель банковского платежа может отличаться от наименования Исполнителя только если он прямо указан здесь. ZakonExpert не запрашивает SMS-коды, пароли и доступ к банковскому приложению."), size=7.45)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(2)
    _font(p.add_run("ПОДПИСИ СТОРОН"), size=8.8, bold=True, family=UI_FONT)
    signs = doc.add_table(rows=2, cols=2)
    _table(signs, [CONTENT_W_MM / 2, CONTENT_W_MM / 2])
    for cell, text in zip(signs.rows[0].cells, ("ИСПОЛНИТЕЛЬ", "КЛИЕНТ"), strict=True):
        _shade(cell, INK)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        _font(cell.paragraphs[0].add_run(text), size=8.3, bold=True, color=WHITE, family=UI_FONT)
    exec_cell, client_cell = signs.rows[1].cells
    exec_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    client_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    _cell_margins(exec_cell, top=80, start=95, bottom=60, end=95)
    _cell_margins(client_cell, top=80, start=120, bottom=60, end=120)
    _font(exec_cell.paragraphs[0].add_run("Руководитель"), size=8.0, bold=True)
    mark = exec_cell.add_paragraph()
    mark.alignment = WD_ALIGN_PARAGRAPH.CENTER
    mark.paragraph_format.space_before = Pt(0)
    mark.paragraph_format.space_after = Pt(0)
    mark.add_run("{{ executor_signature_block }}")
    _font(client_cell.paragraphs[0].add_run("Подпись Клиента"), size=8.0, bold=True)
    raw = client_cell.add_paragraph()
    raw.paragraph_format.space_after = Pt(3)
    _font(raw.add_run("{{ client_signature }}"), size=8)
    line = client_cell.add_paragraph()
    line.paragraph_format.space_after = Pt(4)
    _font(line.add_run("__________________ / {{ client_full_name }} /"), size=8.2)
    date = client_cell.add_paragraph()
    date.paragraph_format.space_after = Pt(0)
    _font(date.add_run("Дата: {{ client_signature_date }}"), size=8.2)
    _keep(signs.rows[1])

    end = doc.add_paragraph()
    end.alignment = WD_ALIGN_PARAGRAPH.CENTER
    end.paragraph_format.space_before = Pt(2)
    end.paragraph_format.space_after = Pt(0)
    _font(end.add_run("Перед подписанием Клиент подтверждает, что прочитал ключевые условия, понимает объём услуг, цену, порядок оплаты и правила возврата."), size=7.15, italic=True, color=MUTED)


def build_master_template(output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    _set_defaults(doc)
    doc.core_properties.title = "Договор оказания услуг ZakonExpert"
    doc.core_properties.subject = SCHEMA_MARKER
    doc.core_properties.author = "ТОО «ZakonExpert»"
    _header_footer(doc)
    _page1(doc)
    _page2(doc)
    _page3(doc)
    with tempfile.NamedTemporaryFile(
        prefix="master_v2_", suffix=".docx", dir=output_path.parent, delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)
    try:
        doc.save(tmp_path)
        tmp_path.replace(output_path)
    finally:
        tmp_path.unlink(missing_ok=True)
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

"""Builds the master docxtpl template used for every ZakonExpert contract type.

The legal skeleton (structure, clause wording, requisites layout) is adapted from the
IP ZakonExpert's real, already-in-use contract text; only the parts that legitimately vary
per contract (subject, actions, result, price, payment terms, work period) are Jinja
placeholders. Run this script once (or after a deliberate template revision) to (re)generate
app/templates/contracts/master_v1.docx.
"""
from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.document import Document as DocumentObject
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "app" / "templates" / "contracts" / "master_v1.docx"

BODY_FONT = "Times New Roman"
BODY_SIZE = Pt(12)


def _set_base_style(document: DocumentObject) -> None:
    style = document.styles["Normal"]
    style.font.name = BODY_FONT
    style.font.size = BODY_SIZE
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), BODY_FONT)

    section = document.sections[0]
    section.page_height = Mm(297)
    section.page_width = Mm(210)
    section.top_margin = Mm(20)
    section.bottom_margin = Mm(20)
    section.left_margin = Mm(20)
    section.right_margin = Mm(15)


def _add_page_numbers(document: DocumentObject) -> None:
    section = document.sections[0]
    footer = section.footer
    paragraph = footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    fld_begin = run._r.makeelement(qn("w:fldChar"), {qn("w:fldCharType"): "begin"})
    run._r.append(fld_begin)
    instr = run._r.makeelement(qn("w:instrText"), {qn("xml:space"): "preserve"})
    instr.text = "PAGE"
    run._r.append(instr)
    fld_end = run._r.makeelement(qn("w:fldChar"), {qn("w:fldCharType"): "end"})
    run._r.append(fld_end)


def _heading(document: DocumentObject, text: str, size: int = 13) -> None:
    p = document.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(size)
    p.paragraph_format.space_after = Pt(8)


def _body(document: DocumentObject, text: str, *, bold_lead: str | None = None, justify: bool = True) -> None:
    p = document.add_paragraph()
    if justify:
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.15
    if bold_lead:
        lead_run = p.add_run(bold_lead)
        lead_run.bold = True
    p.add_run(text)


def _section_title(document: DocumentObject, number: str, title: str) -> None:
    p = document.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(f"{number}. {title}")
    run.bold = True
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(6)


def build() -> None:
    document = Document()
    _set_base_style(document)
    _add_page_numbers(document)

    _heading(document, "ДОГОВОР ОКАЗАНИЯ УСЛУГ № {{ contract_number }}", size=15)

    date_line = document.add_paragraph()
    date_line.alignment = WD_ALIGN_PARAGRAPH.LEFT
    tab_stops = date_line.paragraph_format.tab_stops
    tab_stops.add_tab_stop(Cm(16))
    date_line.add_run("{{ contract_city }}\t«{{ contract_date }}»")

    document.add_paragraph()

    _body(
        document,
        "{{ executor_full_name }}, осуществляющий деятельность под коммерческим "
        "обозначением {{ executor_brand_name }}, ИИН {{ executor_iin }}, именуемый в "
        "дальнейшем «Исполнитель», с одной стороны, и {{ client_full_name }}, ИИН "
        "{{ client_iin }}, телефон/WhatsApp: {{ client_phone }}, именуемый в дальнейшем "
        "«Клиент», с другой стороны, совместно именуемые «Стороны», заключили настоящий "
        "договор о нижеследующем.",
    )

    _section_title(document, "1", "ПРЕДМЕТ ДОГОВОРА")
    _body(document, "{{ service_subject }}", bold_lead="1.1. ")
    _body(document, "В состав услуг входят: {{ service_actions }}.", bold_lead="1.2. ")
    _body(
        document,
        "Исполнитель оказывает консультационную, информационную и документальную "
        "поддержку. Настоящий договор не является договором адвокатской помощи; участие "
        "Исполнителя в судебном заседании, нотариальные расходы, государственная пошлина, "
        "услуги медиатора, адвоката или иного представителя оплачиваются отдельно, если "
        "Стороны письменно не согласовали иное.",
        bold_lead="1.3. ",
    )

    _section_title(document, "2", "РЕЗУЛЬТАТ И ПОРЯДОК ОКАЗАНИЯ УСЛУГ")
    _body(
        document,
        "Результатом услуг по настоящему договору признаётся {{ result_definition }}. "
        "Если договором предусмотрено несколько допустимых результатов, для признания "
        "услуг оказанными достаточно наступления одного из них при условии подтверждения "
        "официальным документом.",
        bold_lead="2.1. ",
    )
    _body(
        document,
        "Срок оказания услуг: {{ work_period }}. Сроки рассмотрения обращений судом, "
        "нотариусом, ЧСИ, банком, взыскателем и государственными органами не зависят от "
        "Исполнителя и в срок оказания услуг не включаются.",
        bold_lead="2.2. ",
    )
    _body(
        document,
        "Клиент обязан незамедлительно передавать Исполнителю поступившие уведомления, "
        "постановления, судебные извещения, ответы государственных органов и организаций "
        "и иные документы, имеющие отношение к делу.",
        bold_lead="2.3. ",
    )

    _section_title(document, "3", "СТОИМОСТЬ УСЛУГ И ПОРЯДОК ОПЛАТЫ")
    _body(
        document,
        "Общая стоимость услуг по настоящему договору составляет {{ amount_digits }} "
        "({{ amount_words }}).",
        bold_lead="3.1. ",
    )
    _body(document, "{{ payment_terms }}", bold_lead="3.2. ")
    _body(
        document,
        "Оплата производится наличными либо переводом на Kaspi/банковский счёт "
        "Исполнителя по номеру: {{ executor_phone }}, получатель: {{ executor_name }}. "
        "Факт оплаты подтверждается банковским чеком, квитанцией, распиской либо иным "
        "платёжным документом.",
        bold_lead="3.3. ",
    )
    _body(document, "{{ penalty_clause }}", bold_lead="3.4. ")

    _section_title(document, "4", "ПРАВА И ОБЯЗАННОСТИ СТОРОН")
    _body(
        document,
        "Исполнитель обязуется добросовестно подготовить документы, информировать "
        "Клиента о существенных действиях и передавать Клиенту полученные ответы и "
        "документы.",
        bold_lead="4.1. ",
    )
    _body(
        document,
        "Исполнитель вправе выбирать законный способ защиты интересов Клиента, "
        "запрашивать дополнительные документы и приостанавливать работу до их "
        "предоставления.",
        bold_lead="4.2. ",
    )
    _body(
        document,
        "Клиент обязуется предоставлять достоверные и полные сведения, своевременно "
        "подписывать подготовленные документы, оплачивать обязательные государственные и "
        "нотариальные расходы, лично являться в суд, к нотариусу или ЧСИ, если это "
        "требуется законом или органом, рассматривающим обращение.",
        bold_lead="4.3. ",
    )
    _body(
        document,
        "Клиент подтверждает, что сообщил Исполнителю обо всех известных исполнительных "
        "производствах, судебных актах, соглашениях, платежах, ранее поданных заявлениях "
        "и иных обстоятельствах, влияющих на оказание услуг.",
        bold_lead="4.4. ",
    )

    _section_title(document, "5", "ПРИЕМКА УСЛУГ")
    _body(document, "{{ result_definition }}" and (
        "После достижения предусмотренного договором результата Исполнитель направляет "
        "Клиенту итоговый документ или уведомление о результате посредством Telegram, "
        "WhatsApp или электронной почты. Если Клиент в течение 3 (трёх) календарных дней "
        "не направит мотивированные письменные возражения с указанием конкретных "
        "недостатков, услуги считаются оказанными и принятыми в полном объёме."
    ), bold_lead="5.1. ")
    _body(
        document,
        "Отказ Клиента от подписания акта при наличии доказательств выполнения работ и "
        "отсутствии мотивированных письменных возражений не отменяет факт оказания и "
        "приёмки услуг.",
        bold_lead="5.2. ",
    )

    _section_title(document, "6", "ОТВЕТСТВЕННОСТЬ И РАЗРЕШЕНИЕ СПОРОВ")
    _body(
        document,
        "Стороны несут ответственность в соответствии с законодательством Республики "
        "Казахстан и настоящим договором.",
        bold_lead="6.1. ",
    )
    _body(
        document,
        "Исполнитель не отвечает за незаконные либо несвоевременные действия/бездействие "
        "нотариуса, ЧСИ, суда, взыскателя, банка и государственных органов, но обязуется "
        "подготовить и передать Клиенту документы и рекомендации, предусмотренные "
        "настоящим договором.",
        bold_lead="6.2. ",
    )
    _body(
        document,
        "Стороны признают юридическую силу переписки и документов, переданных через "
        "WhatsApp, Telegram, SMS, электронную почту и иные согласованные средства связи, "
        "если возможно достоверно определить отправителя, содержание и дату сообщения.",
        bold_lead="6.3. ",
    )
    _body(
        document,
        "До обращения в суд заинтересованная Сторона направляет письменную претензию. "
        "Срок ответа на претензию — 5 (пять) рабочих дней с момента её получения. При "
        "недостижении соглашения спор рассматривается в порядке, установленном "
        "законодательством Республики Казахстан.",
        bold_lead="6.4. ",
    )

    _section_title(document, "7", "ПЕРСОНАЛЬНЫЕ ДАННЫЕ И УВЕДОМЛЕНИЯ")
    _body(
        document,
        "Подписывая настоящий договор, Клиент даёт согласие на сбор и обработку "
        "Исполнителем своих персональных данных в объёме, необходимом для исполнения "
        "настоящего договора, в соответствии с законодательством Республики Казахстан о "
        "персональных данных и их защите.",
        bold_lead="7.1. ",
    )
    _body(
        document,
        "Уведомления и сообщения по настоящему договору направляются по телефону, "
        "WhatsApp, Telegram или электронной почте, указанным Сторонами, и считаются "
        "полученными в день отправки.",
        bold_lead="7.2. ",
    )

    _section_title(document, "8", "ЗАКЛЮЧИТЕЛЬНЫЕ ПОЛОЖЕНИЯ")
    _body(
        document,
        "Настоящий договор вступает в силу с даты его подписания и действует до полного "
        "исполнения Сторонами обязательств.",
        bold_lead="8.1. ",
    )
    _body(
        document,
        "Изменения и дополнения действительны при письменном согласовании Сторонами, "
        "включая согласование через WhatsApp, Telegram или электронную переписку.",
        bold_lead="8.2. ",
    )
    _body(
        document,
        "Договор составлен в двух экземплярах, имеющих одинаковую юридическую силу, по "
        "одному для каждой из Сторон, либо подписан посредством простой электронной "
        "подписи Клиента в соответствии с порядком, доведённым до сведения Клиента при "
        "подписании.",
        bold_lead="8.3. ",
    )

    document.add_page_break()
    _section_title(document, "9", "РЕКВИЗИТЫ И ПОДПИСИ СТОРОН")

    table = document.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    for column in table.columns:
        column.width = Cm(8.5)

    header_cells = table.rows[0].cells
    left = header_cells[0].paragraphs[0]
    left.add_run("ИСПОЛНИТЕЛЬ").bold = True
    right = header_cells[1].paragraphs[0]
    right.add_run("КЛИЕНТ").bold = True

    row = table.add_row().cells
    left_p = row[0].paragraphs[0]
    left_p.add_run(
        "{{ executor_brand_name }}\n"
        "{{ executor_full_name }}\n"
        "ИИН: {{ executor_iin }}\n"
        "Адрес: {{ executor_address }}\n"
        "Тел./WhatsApp: {{ executor_phone }}\n"
        "Kaspi: {{ executor_phone }}"
    )
    right_p = row[1].paragraphs[0]
    right_p.add_run(
        "{{ client_full_name }}\n"
        "ИИН: {{ client_iin }}\n"
        "Телефон/WhatsApp: {{ client_phone }}\n"
        "Адрес: {{ client_address }}"
    )

    for _ in range(3):
        document.add_paragraph()

    sig_table = document.add_table(rows=1, cols=2)
    sig_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for column in sig_table.columns:
        column.width = Cm(8.5)
    sig_row = sig_table.rows[0].cells
    for cell in sig_row:
        cell.height = Cm(5)

    exec_cell_p = sig_row[0].paragraphs[0]
    exec_cell_p.add_run("Подпись: {{ executor_signature }}\n").font.size = Pt(11)
    exec_cell_p.add_run("М.П.: {{ executor_stamp }}")

    client_cell_p = sig_row[1].paragraphs[0]
    client_cell_p.add_run(
        "Подпись (простая электронная подпись): {{ client_signature }}\n\n"
        "Дата подписания: {{ client_signature_date }}"
    ).font.size = Pt(11)

    document.add_paragraph()
    footer_note = document.add_paragraph()
    footer_note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    note_run = footer_note.add_run(
        "Простая электронная подпись Клиента фиксируется системой ZakonExpert Bot с "
        "указанием даты, времени, IP-адреса и хеша документа и не является усиленной "
        "квалифицированной электронной подписью (ЭЦП)."
    )
    note_run.italic = True
    note_run.font.size = Pt(9)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(OUTPUT_PATH))
    print(f"Master template written to {OUTPUT_PATH}")


if __name__ == "__main__":
    build()
    sys.exit(0)

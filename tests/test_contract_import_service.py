from __future__ import annotations

from app.services.contract_import_service import parse_contract_text


def test_parse_current_zakonexpert_contract_layout() -> None:
    text = """
    ZAKONEXPERT
    ДОГОВОР ОКАЗАНИЯ УСЛУГ
    НОМЕР ДОГОВОРА | № 741
    МЕСТО ЗАКЛЮЧЕНИЯ | г. Талдыкорган
    ДАТА | 31.08.2026 г.

    ИСПОЛНИТЕЛЬ | КЛИЕНТ
    ТОО «ZakonExpert» | Иванов Иван Иванович
    БИН 260740044168 | ИИН 900101300123 · +7 700 123 45 67

    КЛЮЧЕВЫЕ УСЛОВИЯ
    01 | УСЛУГА | Подготовка заявления на изменение условий договора и графика платежей
    02 | РЕЗУЛЬТАТ | Подготовленный пакет документов
    03 | СРОК | до 30 календарных дней
    04 | СТОИМОСТЬ | 50 000 тенге (пятьдесят тысяч тенге)
    05 | ОПЛАТА | Оплата производится до начала оказания услуг.

    КЛИЕНТ
    Иванов Иван Иванович
    ИИН: 900101300123
    Тел./WhatsApp: +7 700 123 45 67
    Адрес: г. Алматы, ул. Абая, 10
    """

    parsed = parse_contract_text(text)
    assert parsed["name"] == "Иванов Иван Иванович"
    assert parsed["iin"] == "900101300123"
    assert parsed["phone"] == "+77001234567"
    assert parsed["number"] == "741"
    assert parsed["date"] == "2026-08-31"
    assert parsed["amount"] == 50000
    assert "Подготовка заявления" in parsed["service"]
    assert parsed["address"].startswith("г. Алматы")
    assert parsed["paymentType"] == "prepayment"


def test_parser_does_not_use_executor_bin_as_client_iin() -> None:
    text = """
    ДОГОВОР № 18 от 30.08.2026
    Исполнитель: ТОО ZakonExpert, БИН 260740044168
    Заказчик: Петров Петр Петрович, ИИН: 880202350987, Телефон: +7 701 555 44 33
    Стоимость услуг: 100 000 тенге
    """
    parsed = parse_contract_text(text)
    assert parsed["iin"] == "880202350987"
    assert parsed["phone"] == "+77015554433"
    assert parsed["amount"] == 100000

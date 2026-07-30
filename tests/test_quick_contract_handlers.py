from __future__ import annotations

import pytest

from app.bot.handlers.quick_contract import (
    _looks_like_quick_contract_request,
    _looks_like_quick_text_request,
)


@pytest.mark.parametrize(
    "caption",
    [
        "+7 702 242 4487, отмена ареста от ЧСИ, стоимость 20 000 тенге, оплата после результата",
        "Снятие ареста и отмена исполнительной надписи. 120К, деньги сразу. Телефон +7 701 234 5678",
        "Отмена судебного решения, клиент в суде не участвовал. Цена 150 000, предоплата 50%",
        "Нужно направить ЧСИ требование о снятии ограничений. 20 000 тенге сразу",
    ],
)
def test_recognizes_quick_contract_captions(caption: str) -> None:
    assert _looks_like_quick_contract_request(caption) is True


@pytest.mark.parametrize("caption", [None, "", "просто фото без контекста", "привет как дела"])
def test_does_not_misfire_on_unrelated_captions(caption: str | None) -> None:
    assert _looks_like_quick_contract_request(caption) is False


@pytest.mark.parametrize(
    "text",
    [
        "ФИО: ТЮ ОЛЕГ ВИКТОРОВИЧ, ИИН: 731121302594",
        "ТЮ ОЛЕГ ВИКТОРОВИЧ 731121302594 снятие ареста, 60К, оплата сразу",
    ],
)
def test_recognizes_text_identity_contract_request(text: str) -> None:
    assert _looks_like_quick_text_request(text) is True


@pytest.mark.parametrize("text", ["Привет", "Снятие ареста 50000", "731121302594"])
def test_does_not_autostart_text_flow_without_name_and_iin(text: str) -> None:
    assert _looks_like_quick_text_request(text) is False

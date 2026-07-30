from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.conditions import ContractConditions
from app.services.openai_service import OpenAIService, OpenAIUnavailableError


def test_service_disabled_without_api_key() -> None:
    service = OpenAIService()
    assert service.is_enabled is False


async def test_extract_identity_raises_when_disabled() -> None:
    service = OpenAIService()
    with pytest.raises(OpenAIUnavailableError):
        await service.extract_identity_data(image_bytes=b"fake", mime_type="image/jpeg")


async def test_extract_conditions_raises_when_disabled() -> None:
    service = OpenAIService()
    with pytest.raises(OpenAIUnavailableError):
        await service.extract_contract_conditions(employee_text="test")


async def test_draft_contract_narrative_raises_when_disabled() -> None:
    service = OpenAIService()
    with pytest.raises(OpenAIUnavailableError):
        await service.draft_contract_narrative(
            conditions=ContractConditions(service_type="x"),
            base_subject="базовый предмет",
            base_actions="базовые действия",
        )


def test_validate_identity_rejects_bad_iin() -> None:
    with pytest.raises(ValidationError):
        OpenAIService.validate_identity({"iin": "123"})


def test_validate_conditions_rejects_missing_required_field() -> None:
    with pytest.raises(ValidationError):
        OpenAIService.validate_conditions({"amount_kzt": 1000})


@pytest.mark.parametrize(
    "text,expected_template",
    [
        ("снятие ареста от ЧСИ", "arrest_lift_chsi"),
        ("отмена исполнительной надписи нотариуса", "notarial_writ_cancel"),
        ("снятие запрета на выезд", "travel_ban_lift"),
        ("составление графика погашения задолженности", "debt_schedule"),
        ("медиативное соглашение с банком", "mediation_agreement"),
        ("обжалование штрафа", "fine_appeal"),
    ],
)
def test_suggest_template_heuristics(text: str, expected_template: str) -> None:
    conditions = ContractConditions(service_type=text)
    assert OpenAIService.suggest_template(conditions) == expected_template


def test_suggest_template_prefers_explicit_code() -> None:
    conditions = ContractConditions(service_type="что угодно", template_code="fine_appeal")
    assert OpenAIService.suggest_template(conditions) == "fine_appeal"


def test_suggest_template_reclassifies_generic_model_fallback() -> None:
    conditions = ContractConditions(
        service_type="Снятие арестов от ЧСИ",
        template_code="custom_approved",
    )
    assert OpenAIService.suggest_template(conditions) == "arrest_lift_chsi"
    assert "АИС ОИП" in OpenAIService.suggest_result_definition(conditions)


def test_suggest_result_definition_prefers_explicit_value() -> None:
    conditions = ContractConditions(service_type="x", result_definition="явный результат")
    assert OpenAIService.suggest_result_definition(conditions) == "явный результат"

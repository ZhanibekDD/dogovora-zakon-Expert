from __future__ import annotations

import pytest

from app.database.models.client import Client
from app.database.models.contract import Contract
from app.schemas.conditions import ContractConditions
from app.schemas.contract_narrative import ContractNarrative
from app.services import contract_service
from app.services.openai_service import OpenAIService, OpenAIUnavailableError


def _conditions(**overrides) -> ContractConditions:
    base = dict(
        service_type="снятие ареста от ЧСИ",
        amount_kzt=50000,
        payment_type="after_result",
        template_code="arrest_lift_chsi",
    )
    base.update(overrides)
    return ContractConditions(**base)


def _contract_and_client() -> tuple[Contract, Client]:
    contract = Contract(contract_number=1)
    client = Client(full_name="Тестов Тест Тестович", iin="010312500019")
    return contract, client


async def test_draft_narrative_noop_when_openai_disabled() -> None:
    conditions = _conditions()
    await contract_service.draft_narrative_for_conditions(OpenAIService(), conditions)
    assert conditions.subject_paragraph is None
    assert conditions.actions_paragraph is None


class _RaisingOpenAIService(OpenAIService):
    """Pretends to be enabled but always fails the narrative call, to exercise the
    fallback-to-preset-text path without hitting the real OpenAI API."""

    def __init__(self, exc: Exception) -> None:
        self._enabled = True
        self._exc = exc

    async def draft_contract_narrative(self, **kwargs):  # type: ignore[override]
        raise self._exc


async def test_draft_narrative_falls_back_silently_on_unavailable_error() -> None:
    conditions = _conditions()
    await contract_service.draft_narrative_for_conditions(
        _RaisingOpenAIService(OpenAIUnavailableError("boom")), conditions
    )
    assert conditions.subject_paragraph is None
    assert conditions.actions_paragraph is None


async def test_draft_narrative_falls_back_silently_on_validation_error() -> None:
    import pydantic

    try:
        ContractNarrative.model_validate({})
    except pydantic.ValidationError as exc:
        validation_error = exc
    else:
        raise AssertionError("expected a ValidationError for the empty payload")

    conditions = _conditions()
    await contract_service.draft_narrative_for_conditions(
        _RaisingOpenAIService(validation_error), conditions
    )
    assert conditions.subject_paragraph is None
    assert conditions.actions_paragraph is None


class _StubOpenAIService(OpenAIService):
    def __init__(self, narrative: ContractNarrative) -> None:
        self._enabled = True
        self._narrative = narrative

    async def draft_contract_narrative(self, **kwargs):  # type: ignore[override]
        return self._narrative


async def test_draft_narrative_applies_result_when_openai_succeeds() -> None:
    conditions = _conditions()
    narrative = ContractNarrative(
        subject_paragraph="Исполнитель обязуется оказать Клиенту услуги по снятию ареста, "
        "наложенного ЧСИ Ержановым Е.Е. в рамках исполнительного производства №123.",
        actions_paragraph="анализ материалов дела; подготовка обращения в адрес ЧСИ Ержанова Е.Е.",
    )
    await contract_service.draft_narrative_for_conditions(_StubOpenAIService(narrative), conditions)
    assert conditions.subject_paragraph == narrative.subject_paragraph
    assert conditions.actions_paragraph == narrative.actions_paragraph


def test_render_context_falls_back_to_preset_when_narrative_absent() -> None:
    contract, client = _contract_and_client()
    conditions = _conditions()
    context = contract_service._build_render_context(contract=contract, client=client, conditions=conditions)
    assert "снятие ареста" in context.service_subject
    assert context.service_subject.startswith("Исполнитель обязуется оказать")


def test_render_context_uses_drafted_narrative_when_present() -> None:
    contract, client = _contract_and_client()
    conditions = _conditions(
        subject_paragraph="Индивидуальный, case-specific текст предмета договора.",
        actions_paragraph="индивидуальный перечень действий",
    )
    context = contract_service._build_render_context(contract=contract, client=client, conditions=conditions)
    assert context.service_subject == "Индивидуальный, case-specific текст предмета договора."
    assert context.service_actions == "индивидуальный перечень действий"


def test_validate_contract_narrative_rejects_missing_field() -> None:
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        OpenAIService.validate_contract_narrative({"subject_paragraph": "x"})

from __future__ import annotations

import datetime
from pathlib import Path

import pydantic
import pytz
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import DEFAULT_PENALTY_CLAUSE, ContractStatus, PaymentType
from app.core.logging import get_logger
from app.core.security import sha256_file
from app.database.models.client import Client
from app.database.models.contract import Contract, ContractTemplate, ContractVersion
from app.database.repositories.counter_repo import reserve_next_contract_number
from app.schemas.conditions import ContractConditions
from app.schemas.contract import ContractRenderContext
from app.schemas.identity import IdentityExtraction
from app.services import document_service, pdf_service, template_service
from app.services.openai_service import OpenAIService, OpenAIUnavailableError
from app.services.storage_service import contract_dir
from app.utils.amount_words import amount_to_words_kzt, format_amount_digits

logger = get_logger(__name__)

PAYMENT_TERMS_TEXT = {
    PaymentType.PREPAYMENT: "Оплата производится в день подписания договора до начала оказания услуг.",
    PaymentType.AFTER_RESULT: (
        "Оплата производится не позднее одного календарного дня после достижения результата, "
        "указанного в п. 1.3 настоящего договора."
    ),
    PaymentType.ALREADY_PAID: (
        "Клиент полностью оплатил стоимость услуг до подписания договора. Исполнитель "
        "подтверждает получение оплаты."
    ),
    PaymentType.CUSTOM: "Порядок оплаты согласован Сторонами отдельно и указан в настоящем пункте.",
}


def now_almaty() -> datetime.datetime:
    settings = get_settings()
    tz = pytz.timezone(settings.timezone)
    return datetime.datetime.now(tz)


def build_payment_terms(conditions: ContractConditions) -> str:
    payment_type = PaymentType(conditions.payment_type)
    if payment_type == PaymentType.SPLIT:
        first = conditions.first_payment_kzt or 0
        second = conditions.second_payment_kzt or 0
        return (
            f"Оплата производится в два этапа: {format_amount_digits(first)} тенге до начала "
            f"оказания услуг, {format_amount_digits(second)} тенге не позднее одного "
            "календарного дня после достижения результата, указанного в п. 1.3 настоящего "
            "договора."
        )
    return PAYMENT_TERMS_TEXT[payment_type]


async def create_client_from_identity(
    session: AsyncSession, identity: IdentityExtraction, *, phone: str | None, address: str | None
) -> Client:
    birth_date = None
    if identity.birth_date:
        day, month, year = identity.birth_date.split(".")
        birth_date = datetime.date(int(year), int(month), int(day))

    client = Client(
        full_name=identity.full_name or "",
        last_name=identity.last_name,
        first_name=identity.first_name,
        middle_name=identity.middle_name,
        iin=identity.iin,
        birth_date=birth_date,
        document_number=identity.document_number,
        phone=phone,
        address=address,
    )
    session.add(client)
    await session.flush()
    return client


async def get_or_create_active_template(session: AsyncSession, template_code: str) -> ContractTemplate:
    from sqlalchemy import select

    result = await session.execute(
        select(ContractTemplate)
        .where(ContractTemplate.code == template_code, ContractTemplate.is_active.is_(True))
        .order_by(ContractTemplate.version.desc())
    )
    template = result.scalars().first()
    if template is None:
        preset = template_service.get_preset(template_code)
        settings = get_settings()
        template = ContractTemplate(
            code=template_code,
            name=preset.name,
            version=1,
            docx_path=str(settings.templates_dir / "master_v1.docx"),
            is_active=True,
        )
        session.add(template)
        await session.flush()
    return template


async def create_draft_contract(
    session: AsyncSession,
    *,
    manager_id: int,
    client: Client,
    conditions: ContractConditions,
    template_code: str,
) -> Contract:
    settings = get_settings()
    template = await get_or_create_active_template(session, template_code)
    contract_number = await reserve_next_contract_number(session, settings.contract_number_start)

    contract = Contract(
        contract_number=contract_number,
        status=ContractStatus.DRAFT.value,
        template_id=template.id,
        client_id=client.id,
        manager_id=manager_id,
        amount=conditions.amount_kzt or 0,
        currency="KZT",
        payment_type=conditions.payment_type,
        payment_status="pending",
        service_data=conditions.model_dump(),
        result_data={},
        version=1,
    )
    session.add(contract)
    await session.flush()
    return contract


async def draft_narrative_for_conditions(
    openai_service: OpenAIService, conditions: ContractConditions
) -> None:
    """Best-effort case-specific drafting for clauses 1.1/1.2.

    The rest of the approved legal skeleton is deterministic and never delegated to the model.
    """
    if not openai_service.is_enabled:
        return
    preset = template_service.get_preset(conditions.template_code or "custom_approved")
    try:
        narrative = await openai_service.draft_contract_narrative(
            conditions=conditions, base_subject=preset.subject, base_actions=preset.actions
        )
    except (OpenAIUnavailableError, pydantic.ValidationError):
        logger.warning("contract_narrative_drafting_failed")
        return
    conditions.subject_paragraph = narrative.subject_paragraph
    conditions.actions_paragraph = narrative.actions_paragraph


def _build_render_context(
    *, contract: Contract, client: Client, conditions: ContractConditions
) -> ContractRenderContext:
    settings = get_settings()
    template_code = OpenAIService.suggest_template(conditions)
    preset = template_service.get_preset(template_code)
    result_definition = OpenAIService.suggest_result_definition(conditions)
    amount = int(conditions.amount_kzt or 0)
    payment_purpose = (
        f"{settings.executor_bank_payment_purpose} № {contract.contract_number}"
        if settings.executor_bank_payment_purpose
        else f"Оплата по договору № {contract.contract_number}"
    )

    return ContractRenderContext(
        contract_number=contract.contract_number,
        contract_date=now_almaty().strftime("%d.%m.%Y"),
        contract_city=settings.contract_city,
        client_full_name=client.full_name,
        client_iin=client.iin or "",
        client_phone=conditions.client_phone or client.phone or "",
        client_address=client.address or "не указан",
        service_subject=conditions.subject_paragraph or preset.subject,
        service_actions=conditions.actions_paragraph or preset.actions,
        result_definition=result_definition,
        amount_digits=f"{format_amount_digits(amount)} тенге",
        amount_words=amount_to_words_kzt(amount),
        payment_terms=build_payment_terms(conditions),
        work_period=(
            conditions.work_period
            or "до 30 календарных дней с даты получения полного комплекта документов и оплаты"
        ),
        penalty_clause=DEFAULT_PENALTY_CLAUSE,
        executor_name=settings.executor_display_name,
        executor_full_name=settings.executor_full_name,
        executor_brand_name=settings.executor_brand_name,
        executor_identifier_label=settings.executor_identifier_label,
        executor_identifier=settings.executor_identifier,
        executor_director_name=settings.executor_director_name,
        executor_signer_short_name=settings.executor_signer_short_name,
        executor_phone=settings.executor_phone,
        executor_address=settings.executor_address,
        executor_website=settings.executor_website,
        executor_payment_details=settings.executor_payment_details,
        executor_bank_beneficiary=settings.executor_bank_beneficiary,
        executor_bank_beneficiary_identifier=settings.executor_bank_beneficiary_identifier,
        executor_bank_name=settings.executor_bank_name,
        executor_bank_bic=settings.executor_bank_bic,
        executor_bank_iban=settings.executor_bank_iban,
        executor_bank_payment_purpose=payment_purpose,
        executor_kaspi_number=settings.executor_kaspi_number,
        executor_kaspi_receiver=settings.executor_kaspi_receiver,
    )


async def approve_contract_documents(
    session: AsyncSession, contract: Contract, client: Client, approved_by_id: int
) -> tuple[str, str]:
    """Render the final DOCX/PDF with the executor's signature and stamp inserted."""
    conditions = ContractConditions.model_validate(contract.service_data)
    context = _build_render_context(contract=contract, client=client, conditions=conditions)
    template = await session.get(ContractTemplate, contract.template_id)
    assert template is not None, "contract.template_id must reference an existing template"
    directory = contract_dir(contract.id)

    docx_path = directory / f"final_v{contract.version}.docx"
    pdf_path = directory / f"final_v{contract.version}.pdf"

    document_service.render_contract_docx(
        template_docx_path=Path(template.docx_path),
        context=context,
        output_path=docx_path,
        include_executor_signature=True,
    )
    pdf_service.convert_docx_to_pdf(docx_path, pdf_path)

    contract.docx_path = str(docx_path)
    contract.pdf_path = str(pdf_path)
    contract.document_sha256 = sha256_file(str(pdf_path))
    contract.status = ContractStatus.APPROVED.value
    contract.approved_by_id = approved_by_id
    contract.approved_at = now_almaty().replace(tzinfo=None)

    session.add(
        ContractVersion(
            contract_id=contract.id,
            version=contract.version,
            service_data=contract.service_data,
            result_data=contract.result_data,
            docx_path=str(docx_path),
            pdf_path=str(pdf_path),
            sha256=contract.document_sha256,
            created_by_id=approved_by_id,
        )
    )
    await session.flush()
    return str(docx_path), str(pdf_path)

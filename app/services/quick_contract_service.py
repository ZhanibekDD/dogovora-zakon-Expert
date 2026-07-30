from __future__ import annotations

import asyncio
import dataclasses
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.models.client import Client
from app.database.models.contract import Contract
from app.schemas.conditions import ContractConditions
from app.schemas.edit_instruction import ContractEditInstruction
from app.schemas.identity import IdentityExtraction
from app.services import contract_service
from app.services.openai_service import OpenAIService
from app.utils.validators import is_valid_iin_format

MISSING_FIELD_LABELS = {
    "full_name": "ФИО клиента (не удалось распознать на удостоверении)",
    "iin": "ИИН клиента (не удалось распознать на удостоверении)",
    "service_type": "Какая именно услуга требуется?",
    "amount": "Стоимость услуги",
    "payment_type": "Оплата сразу или после результата?",
    "phone": "Номер телефона клиента",
}

PAYMENT_LABELS = {
    "prepayment": "предоплата до начала работ",
    "after_result": "после результата",
    "split": "50/50 (часть сразу, часть после результата)",
    "already_paid": "уже оплачено клиентом",
    "custom": "по договорённости",
}

_AMOUNT_RE = re.compile(r"(\d[\d\s]{2,}\d)\s*(?:тенге|тг|kzt)?", re.IGNORECASE)
_PHONE_RE = re.compile(r"(\+?\d[\d \-]{8,}\d)")
_FILENAME_FORBIDDEN_RE = re.compile(r'[\\/:*?"<>|]')


def build_display_filename(*, contract_number: int, client_full_name: str, amount_kzt: int | None) -> str:
    """Human-readable base name (no extension) shown to the employee in Telegram, e.g.
    'Договор оказания услуг № 9 Турсынбаев Досжан 20000 тенге'. Only the display name changes -
    the file on disk keeps its internal path/name (final_v{version}.docx/pdf)."""
    amount_part = f"{int(amount_kzt)} тенге" if amount_kzt else "сумма не указана"
    raw = f"Договор оказания услуг № {contract_number} {client_full_name} {amount_part}"
    return _FILENAME_FORBIDDEN_RE.sub("", raw).strip()


class ContractAlreadySignedError(Exception):
    """Raised when a reply-edit or deletion targets a contract the client already signed."""


@dataclasses.dataclass
class QuickContractOutcome:
    missing_fields: list[str]
    contract: Contract | None = None
    client: Client | None = None
    docx_path: str | None = None
    pdf_path: str | None = None
    requires_manual_review: bool = False
    pending_payload: dict | None = None


def detect_missing_required_fields(
    identity: IdentityExtraction, conditions: ContractConditions, *, require_phone: bool
) -> list[str]:
    """Only the fields that are truly required to produce a legally usable draft. Birth date,
    address, document number and expiry are deliberately NOT checked here - the quick flow
    must never block on them."""
    missing: list[str] = []
    if not (identity.full_name or "").strip():
        missing.append("full_name")
    if not identity.iin or not is_valid_iin_format(identity.iin):
        missing.append("iin")
    if not (conditions.service_type or "").strip():
        missing.append("service_type")
    if not conditions.amount_kzt or conditions.amount_kzt <= 0:
        missing.append("amount")
    if conditions.payment_type == "custom":
        missing.append("payment_type")
    if require_phone and not (conditions.client_phone or "").strip():
        missing.append("phone")
    return missing


def build_clarification_message(missing_fields: list[str]) -> str:
    lines = ["Не хватает данных для договора:"]
    for idx, field in enumerate(missing_fields, start=1):
        lines.append(f"{idx}. {MISSING_FIELD_LABELS.get(field, field)}")
    lines.append('\nОтветьте одним сообщением, например: "50 000 тенге, оплата после результата".')
    return "\n".join(lines)


def build_success_message(
    *, contract: Contract, client: Client, conditions: ContractConditions, requires_manual_review: bool
) -> str:
    contract_date = contract_service.now_almaty().strftime("%d.%m.%Y")
    payment_label = PAYMENT_LABELS.get(conditions.payment_type, conditions.payment_type)
    lines = [f"Готово: договор № {contract.contract_number} от {contract_date}.", ""]
    if requires_manual_review:
        lines.insert(0, "⚠️ Проверьте ФИО и ИИН перед утверждением.\n")
    lines += [
        f"Клиент: {client.full_name}",
        f"ИИН: {client.iin or '—'}",
        f"Услуга: {conditions.service_type}",
        f"Стоимость: {conditions.amount_kzt or 0} тенге",
        f"Оплата: {payment_label}",
        f"Телефон: {conditions.client_phone or client.phone or 'не указан'}",
        "",
        "Файлы договора приложены ниже.",
    ]
    return "\n".join(lines)


async def extract_identity_and_conditions(
    openai_service: OpenAIService,
    *,
    image_bytes: bytes,
    mime_type: str,
    caption: str,
    extra_images: list[tuple[bytes, str]] | None = None,
) -> tuple[IdentityExtraction, ContractConditions]:
    """One call for identity (vision) + one linked call for conditions (text), run
    concurrently since they are independent extractions over different inputs."""
    if not openai_service.is_enabled:
        return IdentityExtraction(), ContractConditions(service_type=(caption or "").strip())

    identity_task = openai_service.extract_identity_data(
        image_bytes=image_bytes, mime_type=mime_type, extra_images=extra_images
    )
    if (caption or "").strip():
        conditions_task = openai_service.extract_contract_conditions(employee_text=caption)
        identity, conditions = await asyncio.gather(identity_task, conditions_task)
    else:
        identity = await identity_task
        conditions = ContractConditions(service_type="")
    return identity, conditions


def _merge_conditions(old: ContractConditions, new: ContractConditions) -> ContractConditions:
    merged = old.model_copy(deep=True)
    if new.amount_kzt:
        merged.amount_kzt = new.amount_kzt
    if new.payment_type and new.payment_type != "custom":
        merged.payment_type = new.payment_type
    if new.first_payment_kzt:
        merged.first_payment_kzt = new.first_payment_kzt
    if new.second_payment_kzt:
        merged.second_payment_kzt = new.second_payment_kzt
    if new.client_phone:
        merged.client_phone = new.client_phone
    if new.work_period:
        merged.work_period = new.work_period
    if not merged.service_type and new.service_type:
        merged.service_type = new.service_type
    if new.result_definition:
        merged.result_definition = new.result_definition
    if new.template_code:
        merged.template_code = new.template_code
    merged.service_details = list({*merged.service_details, *new.service_details})
    merged.additional_conditions = list({*merged.additional_conditions, *new.additional_conditions})
    merged.warnings = list({*merged.warnings, *new.warnings})
    return merged


def _apply_manual_answer_heuristics(conditions: ContractConditions, answer_text: str) -> ContractConditions:
    """Best-effort regex fallback used only when OPENAI_API_KEY is not configured."""
    merged = conditions.model_copy(deep=True)
    amount_match = _AMOUNT_RE.search(answer_text)
    if amount_match:
        digits = re.sub(r"\D", "", amount_match.group(1))
        if digits:
            merged.amount_kzt = int(digits)

    lowered = answer_text.lower()
    if "после" in lowered:
        merged.payment_type = "after_result"
    elif "сраз" in lowered or "предоплат" in lowered:
        merged.payment_type = "prepayment"
    elif "уже оплат" in lowered:
        merged.payment_type = "already_paid"

    phone_match = _PHONE_RE.search(answer_text)
    if phone_match:
        merged.client_phone = phone_match.group(1)

    if not merged.service_type.strip():
        merged.service_type = answer_text.strip()[:255]

    return merged


async def generate_contract_immediately(
    session: AsyncSession,
    *,
    openai_service: OpenAIService,
    identity: IdentityExtraction,
    conditions: ContractConditions,
    manager_id: int,
) -> tuple[Contract, Client, str, str]:
    """Quick mode skips the separate draft/watermark/'Утвердить' stage entirely: the
    executor's signature and stamp are embedded and the document is finalized in one step,
    with the employee who created it recorded as the approver. (The detailed mode in
    new_contract.py/draft_actions.py still uses the slower draft -> explicit approval path
    for cases where that extra review step is wanted.)"""
    client = await contract_service.create_client_from_identity(
        session, identity, phone=conditions.client_phone, address=None
    )

    if not conditions.template_code:
        conditions.template_code = OpenAIService.suggest_template(conditions)
    if not conditions.result_definition:
        conditions.result_definition = OpenAIService.suggest_result_definition(conditions)
    await contract_service.draft_narrative_for_conditions(openai_service, conditions)

    contract = await contract_service.create_draft_contract(
        session,
        manager_id=manager_id,
        client=client,
        conditions=conditions,
        template_code=conditions.template_code,
    )
    docx_path, pdf_path = await contract_service.approve_contract_documents(
        session, contract, client, approved_by_id=manager_id
    )
    return contract, client, docx_path, pdf_path


async def process_quick_contract_message(
    session: AsyncSession,
    *,
    openai_service: OpenAIService,
    image_bytes: bytes,
    mime_type: str,
    caption: str,
    manager_id: int,
    extra_images: list[tuple[bytes, str]] | None = None,
) -> QuickContractOutcome:
    """The main quick-mode entry point: one photo/PDF + one caption in, a finished draft
    (or a single compact clarification question) out."""
    identity, conditions = await extract_identity_and_conditions(
        openai_service,
        image_bytes=image_bytes,
        mime_type=mime_type,
        caption=caption,
        extra_images=extra_images,
    )
    settings = get_settings()
    missing = detect_missing_required_fields(
        identity, conditions, require_phone=settings.quick_mode_require_phone
    )
    requires_manual_review = identity.requires_manual_review()

    if missing:
        return QuickContractOutcome(
            missing_fields=missing,
            requires_manual_review=requires_manual_review,
            pending_payload={
                "identity": identity.model_dump(),
                "conditions": conditions.model_dump(),
                "manager_id": manager_id,
            },
        )

    contract, client, docx_path, pdf_path = await generate_contract_immediately(
        session, openai_service=openai_service, identity=identity, conditions=conditions, manager_id=manager_id
    )
    return QuickContractOutcome(
        missing_fields=[],
        contract=contract,
        client=client,
        docx_path=docx_path,
        pdf_path=pdf_path,
        requires_manual_review=requires_manual_review,
    )


async def merge_clarification_answer(
    session: AsyncSession,
    *,
    openai_service: OpenAIService,
    pending: dict,
    answer_text: str,
) -> QuickContractOutcome:
    """Continue building the same draft after the employee answered the one compact
    clarification question, without re-uploading the ID document."""
    identity = IdentityExtraction.model_validate(pending["identity"])
    conditions = ContractConditions.model_validate(pending["conditions"])
    manager_id = pending["manager_id"]

    if openai_service.is_enabled:
        combined_text = f"{conditions.service_type}\n{answer_text}".strip()
        refreshed = await openai_service.extract_contract_conditions(employee_text=combined_text)
        conditions = _merge_conditions(conditions, refreshed)
    else:
        conditions = _apply_manual_answer_heuristics(conditions, answer_text)

    settings = get_settings()
    missing = detect_missing_required_fields(
        identity, conditions, require_phone=settings.quick_mode_require_phone
    )
    requires_manual_review = identity.requires_manual_review()

    if missing:
        return QuickContractOutcome(
            missing_fields=missing,
            requires_manual_review=requires_manual_review,
            pending_payload={
                "identity": identity.model_dump(),
                "conditions": conditions.model_dump(),
                "manager_id": manager_id,
            },
        )

    contract, client, docx_path, pdf_path = await generate_contract_immediately(
        session, openai_service=openai_service, identity=identity, conditions=conditions, manager_id=manager_id
    )
    return QuickContractOutcome(
        missing_fields=[],
        contract=contract,
        client=client,
        docx_path=docx_path,
        pdf_path=pdf_path,
        requires_manual_review=requires_manual_review,
    )


def _manual_edit_instruction_heuristics(text: str) -> ContractEditInstruction:
    """Best-effort regex fallback used only when OPENAI_API_KEY is not configured."""
    edit = ContractEditInstruction()
    amount_match = _AMOUNT_RE.search(text)
    if amount_match:
        digits = re.sub(r"\D", "", amount_match.group(1))
        if digits:
            edit.amount_kzt = int(digits)

    lowered = text.lower()
    if "после" in lowered:
        edit.payment_type = "after_result"
    elif "сраз" in lowered:
        edit.payment_type = "prepayment"

    if "адрес" in lowered and ("убер" in lowered or "удал" in lowered):
        edit.remove_address = True

    if "телефон" in lowered or "номер клиента" in lowered or "номер телефона" in lowered:
        phone_match = _PHONE_RE.search(text)
        if phone_match:
            edit.client_phone = phone_match.group(1)

    return edit


async def revise_contract_from_reply(
    session: AsyncSession,
    *,
    openai_service: OpenAIService,
    contract: Contract,
    client: Client,
    edit_text: str,
    edited_by_id: int,
) -> tuple[str, str]:
    """Apply a natural-language edit instruction (a reply to the draft message) to an
    existing contract: only the fields actually mentioned change, everything else is kept,
    and the final document (signature + stamp embedded, matching quick mode's no-separate-
    approval design) is regenerated immediately under a new version number.

    Blocked once a signing link has been issued ('sent_for_signature') or the client has
    already signed: at that point the client is looking at a specific PDF, and silently
    swapping its content out from under an already-issued link/signature would be wrong."""
    if contract.status in ("signed", "sent_for_signature"):
        raise ContractAlreadySignedError(
            "Договор уже отправлен клиенту на подписание или подписан; изменения невозможны."
        )

    conditions = ContractConditions.model_validate(contract.service_data)

    edit = (
        await openai_service.extract_edit_instruction(instruction_text=edit_text)
        if openai_service.is_enabled
        else _manual_edit_instruction_heuristics(edit_text)
    )

    if edit.amount_kzt:
        conditions.amount_kzt = edit.amount_kzt
    if edit.payment_type:
        conditions.payment_type = edit.payment_type
    if edit.first_payment_kzt:
        conditions.first_payment_kzt = edit.first_payment_kzt
    if edit.second_payment_kzt:
        conditions.second_payment_kzt = edit.second_payment_kzt
    if edit.work_period:
        conditions.work_period = edit.work_period
    if edit.remove_client_phone:
        conditions.client_phone = None
    elif edit.client_phone:
        conditions.client_phone = edit.client_phone
    if edit.result_definition:
        conditions.result_definition = edit.result_definition
    if edit.additional_service_details:
        conditions.service_details = [*conditions.service_details, *edit.additional_service_details]
    if edit.template_code:
        conditions.template_code = edit.template_code
        template = await contract_service.get_or_create_active_template(session, edit.template_code)
        contract.template_id = template.id

    if edit.additional_service_details or edit.template_code:
        await contract_service.draft_narrative_for_conditions(openai_service, conditions)

    contract.service_data = conditions.model_dump()
    contract.amount = conditions.amount_kzt or 0
    contract.payment_type = conditions.payment_type
    contract.version += 1

    if edit.remove_address:
        client.address = None
    if edit.remove_client_phone:
        client.phone = None
    elif edit.client_phone:
        client.phone = edit.client_phone

    return await contract_service.approve_contract_documents(
        session, contract, client, approved_by_id=edited_by_id
    )

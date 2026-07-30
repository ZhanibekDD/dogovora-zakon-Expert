from __future__ import annotations

import dataclasses
import re
import uuid
from pathlib import Path

from docxtpl import DocxTemplate

from app.core.config import get_settings
from app.schemas.objection import NotarialWritExtraction, ObjectionSupplement
from app.services import pdf_service
from app.services.contract_service import now_almaty
from app.services.openai_service import OpenAIService
from app.utils.ru_dates import format_date_long_ru, format_date_short_ru
from app.utils.validators import gender_from_iin, is_valid_iin_format

MISSING_FIELD_LABELS = {
    "debtor_name": "ФИО должника (не удалось распознать)",
    "debtor_iin": "ИИН должника (не удалось распознать)",
    "writ_date": "Дата исполнительной надписи",
    "unique_number": "Уникальный номер исполнительной надписи",
    "registry_number": "Номер в реестре",
    "creditor_name": "Наименование взыскателя",
    "total_amount": "Общая сумма задолженности",
    "client_phone": "Номер телефона клиента (для указания в возражении)",
}

_GENDERED_CLAUSES = {
    "male": {
        "disagree": (
            "С указанной исполнительной надписью не согласен, считаю заявленное требование "
            "спорным, а сумму задолженности необоснованной и подлежащей проверке. "
            "Задолженность не является бесспорной, поскольку я не признаю заявленную сумму "
            "взыскания и не согласен с порядком ее расчета."
        ),
        "not_signed": (
            "Я не подписывал акт сверки, соглашение о признании долга, ответ на претензию "
            "либо иной документ, подтверждающий мое письменное признание суммы "
            "задолженности. Документы, подтверждающие бесспорность требования, мне не "
            "предоставлялись."
        ),
        "learned": (
            "Кроме того, копия исполнительной надписи мне своевременно и надлежащим образом "
            "не вручалась. О наличии исполнительной надписи я узнал только после получения "
            "сведений о взыскании / исполнительном производстве. В связи с этим срок подачи "
            "возражения прошу исчислять с даты фактического получения копии исполнительной "
            "надписи либо сведений о ней."
        ),
    },
    "female": {
        "disagree": (
            "С указанной исполнительной надписью не согласна, считаю заявленное требование "
            "спорным, а сумму задолженности необоснованной и подлежащей проверке. "
            "Задолженность не является бесспорной, поскольку я не признаю заявленную сумму "
            "взыскания и не согласна с порядком ее расчета."
        ),
        "not_signed": (
            "Я не подписывала акт сверки, соглашение о признании долга, ответ на претензию "
            "либо иной документ, подтверждающий мое письменное признание суммы "
            "задолженности. Документы, подтверждающие бесспорность требования, мне не "
            "предоставлялись."
        ),
        "learned": (
            "Кроме того, копия исполнительной надписи мне своевременно и надлежащим образом "
            "не вручалась. О наличии исполнительной надписи я узнала только после получения "
            "сведений о взыскании / исполнительном производстве. В связи с этим срок подачи "
            "возражения прошу исчислять с даты фактического получения копии исполнительной "
            "надписи либо сведений о ней."
        ),
    },
}

_FILENAME_FORBIDDEN_RE = re.compile(r'[\\/:*?"<>|]')


class MissingGenderError(Exception):
    """Raised when the debtor's gender cannot be derived (invalid/absent ИИН) - Russian legal
    text requires gendered verb agreement throughout, so this must be resolved before the
    document is drafted, never guessed from name morphology."""


@dataclasses.dataclass
class ObjectionOutcome:
    missing_fields: list[str]
    docx_path: str | None = None
    pdf_path: str | None = None
    writ: NotarialWritExtraction | None = None
    client_phone: str | None = None
    pending_payload: dict | None = None


def format_amount_tenge(amount: float | None) -> str:
    if amount is None:
        return "0 тенге"
    if float(amount) == int(amount):
        return f"{int(amount):,}".replace(",", " ") + " тенге"
    formatted = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
    return f"{formatted} тенге"


def _initials_signature_line(last_name: str, first_name: str | None, middle_name: str | None) -> str:
    parts = [last_name.strip().capitalize() if last_name else ""]
    initials = "".join(f"{p[0].upper()}." for p in (first_name, middle_name) if p)
    if initials:
        parts.append(initials)
    return " ".join(p for p in parts if p)


def detect_missing_required_fields(writ: NotarialWritExtraction, client_phone: str | None) -> list[str]:
    """Only fields load-bearing enough that the objection would be legally incoherent or
    unusable without them."""
    missing: list[str] = []
    if not (writ.debtor_last_name or writ.debtor_first_name):
        missing.append("debtor_name")
    if not writ.debtor_iin or not is_valid_iin_format(writ.debtor_iin):
        missing.append("debtor_iin")
    if not writ.writ_date:
        missing.append("writ_date")
    if not writ.unique_number:
        missing.append("unique_number")
    if not writ.registry_number:
        missing.append("registry_number")
    if not (writ.creditor_name_genitive or writ.creditor_name_nominative):
        missing.append("creditor_name")
    if not writ.total_amount:
        missing.append("total_amount")
    if not (client_phone or "").strip():
        missing.append("client_phone")
    return missing


def build_clarification_message(missing_fields: list[str]) -> str:
    lines = ["Не хватает данных для возражения:"]
    for idx, field in enumerate(missing_fields, start=1):
        lines.append(f"{idx}. {MISSING_FIELD_LABELS.get(field, field)}")
    lines.append('\nОтветьте одним сообщением, например: "ИИН 930922400071, телефон +7 701 987 6543".')
    return "\n".join(lines)


# Fields shared between NotarialWritExtraction and ObjectionSupplement - anything the
# employee typed manually overwrites what OCR/vision extraction produced (or missed).
_SUPPLEMENT_WRIT_FIELDS = (
    "unique_number", "registry_number", "writ_date",
    "notary_city", "notary_full_name", "notary_license_number", "notary_license_date",
    "debtor_last_name", "debtor_first_name", "debtor_middle_name", "debtor_birth_date",
    "debtor_iin", "debtor_address",
    "creditor_name_nominative", "creditor_name_genitive", "creditor_bin",
    "debt_amount", "fee_amount", "total_amount", "obligation_basis_clause",
)


def apply_supplement(
    writ: NotarialWritExtraction, supplement: ObjectionSupplement
) -> NotarialWritExtraction:
    updated = writ.model_copy(deep=True)
    for field in _SUPPLEMENT_WRIT_FIELDS:
        value = getattr(supplement, field)
        if value is not None:
            setattr(updated, field, value)
    return updated


def build_render_context(
    *, writ: NotarialWritExtraction, client_phone: str, client_email: str | None
) -> dict:
    if not writ.debtor_iin or not is_valid_iin_format(writ.debtor_iin):
        raise MissingGenderError("Невозможно определить пол должника: некорректный или отсутствующий ИИН")
    gender = gender_from_iin(writ.debtor_iin)
    if gender is None:
        raise MissingGenderError("Невозможно определить пол должника по ИИН")
    clauses = _GENDERED_CLAUSES[gender]

    settings = get_settings()
    email = client_email or settings.executor_email or None
    client_email_line = f"\nэл. почта: {email}" if email else ""

    obligation_paragraph = ""
    if writ.obligation_basis_clause:
        obligation_paragraph = (
            f"Из исполнительной надписи следует, что взыскание произведено "
            f"{writ.obligation_basis_clause}. Данные обстоятельства, расчет задолженности, "
            "начисления, расходы и основания взыскания являются спорными и требуют проверки "
            "в судебном порядке при участии сторон."
        )

    creditor_genitive = writ.creditor_name_genitive or writ.creditor_name_nominative or ""

    return {
        "notary_city": writ.notary_city or "",
        "notary_full_name": writ.notary_full_name or "",
        "notary_license_number": writ.notary_license_number or "не указана",
        "notary_license_date": writ.notary_license_date or "не указана",
        "client_full_name": writ.debtor_full_name,
        "client_birth_date": writ.debtor_birth_date or "",
        "client_iin": writ.debtor_iin or "",
        "client_address": writ.debtor_address or "не указан",
        "client_phone": client_phone,
        "client_email_line": client_email_line,
        "writ_date_long": format_date_long_ru(writ.writ_date) if writ.writ_date else "",
        "unique_number": writ.unique_number or "",
        "registry_number": writ.registry_number or "",
        "creditor_name_genitive": creditor_genitive,
        "creditor_bin": writ.creditor_bin or "",
        "debt_amount_text": format_amount_tenge(writ.debt_amount),
        "fee_amount_text": format_amount_tenge(writ.fee_amount),
        "total_amount_text": format_amount_tenge(writ.total_amount),
        "disagree_clause": clauses["disagree"],
        "not_signed_clause": clauses["not_signed"],
        "obligation_paragraph": obligation_paragraph,
        "learned_clause": clauses["learned"],
        "client_signature_line": _initials_signature_line(
            writ.debtor_last_name or "", writ.debtor_first_name, writ.debtor_middle_name
        ),
        "objection_date": format_date_short_ru(now_almaty().date()),
    }


def build_display_filename(*, debtor_last_name: str, client_phone: str) -> str:
    digits = re.sub(r"\D", "", client_phone or "")
    date_part = now_almaty().strftime("%d.%m.%Y")
    surname = (debtor_last_name or "Клиент").strip().capitalize()
    raw = f"Возражение_{surname}_{digits}_{date_part}"
    return _FILENAME_FORBIDDEN_RE.sub("", raw)


def render_objection_docx(context: dict, output_path: Path) -> None:
    settings = get_settings()
    template_path = settings.objection_templates_dir / "objection_v1.docx"
    doc = DocxTemplate(str(template_path))
    doc.render(context)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))


def objection_output_dir() -> Path:
    settings = get_settings()
    directory = settings.objections_dir / str(uuid.uuid4())
    directory.mkdir(parents=True, exist_ok=True)
    return directory


async def generate_objection_files(
    *, writ: NotarialWritExtraction, client_phone: str, client_email: str | None
) -> tuple[str, str]:
    context = build_render_context(writ=writ, client_phone=client_phone, client_email=client_email)
    directory = objection_output_dir()
    docx_path = directory / "objection.docx"
    pdf_path = directory / "objection.pdf"
    render_objection_docx(context, docx_path)
    pdf_service.convert_docx_to_pdf(docx_path, pdf_path)
    return str(docx_path), str(pdf_path)


async def extract_writ_from_image(
    openai_service: OpenAIService,
    *,
    image_bytes: bytes,
    mime_type: str,
    extra_images: list[tuple[bytes, str]] | None = None,
) -> NotarialWritExtraction:
    if not openai_service.is_enabled:
        return NotarialWritExtraction()
    return await openai_service.extract_notarial_writ_data(
        image_bytes=image_bytes, mime_type=mime_type, extra_images=extra_images
    )


async def process_objection_message(
    openai_service: OpenAIService,
    *,
    image_bytes: bytes,
    mime_type: str,
    caption: str,
    extra_images: list[tuple[bytes, str]] | None = None,
) -> ObjectionOutcome:
    """The main entry point: one photo/PDF of the notarial writ + one caption (client's
    phone, optionally email) in, a finished objection DOCX+PDF (or a single compact
    clarification question) out."""
    writ = await extract_writ_from_image(
        openai_service, image_bytes=image_bytes, mime_type=mime_type, extra_images=extra_images
    )
    client_phone, client_email = _parse_contact_from_caption(caption)

    missing = detect_missing_required_fields(writ, client_phone)
    if missing:
        return ObjectionOutcome(
            missing_fields=missing,
            writ=writ,
            pending_payload={
                "writ": writ.model_dump(),
                "client_phone": client_phone,
                "client_email": client_email,
            },
        )

    docx_path, pdf_path = await generate_objection_files(
        writ=writ, client_phone=client_phone, client_email=client_email
    )
    return ObjectionOutcome(
        missing_fields=[], docx_path=docx_path, pdf_path=pdf_path, writ=writ, client_phone=client_phone
    )


async def merge_objection_clarification(
    openai_service: OpenAIService, *, pending: dict, answer_text: str
) -> ObjectionOutcome:
    writ = NotarialWritExtraction.model_validate(pending["writ"])
    client_phone = pending.get("client_phone") or ""
    client_email = pending.get("client_email")

    if openai_service.is_enabled:
        supplement = await openai_service.extract_objection_supplement(employee_text=answer_text)
        writ = apply_supplement(writ, supplement)
        client_phone = supplement.client_phone or client_phone
        client_email = supplement.client_email or client_email
    else:
        manual_phone, manual_email = _parse_contact_from_caption(answer_text)
        client_phone = manual_phone or client_phone
        client_email = manual_email or client_email

    missing = detect_missing_required_fields(writ, client_phone)
    if missing:
        return ObjectionOutcome(
            missing_fields=missing,
            writ=writ,
            pending_payload={
                "writ": writ.model_dump(),
                "client_phone": client_phone,
                "client_email": client_email,
            },
        )

    docx_path, pdf_path = await generate_objection_files(
        writ=writ, client_phone=client_phone, client_email=client_email
    )
    return ObjectionOutcome(
        missing_fields=[], docx_path=docx_path, pdf_path=pdf_path, writ=writ, client_phone=client_phone
    )


_PHONE_RE = re.compile(r"(\+?\d[\d \-]{8,}\d)")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _parse_contact_from_caption(text: str) -> tuple[str, str | None]:
    """Best-effort regex fallback for pulling phone/email out of the caption without OpenAI -
    used both for the initial caption and for manual-mode clarification answers."""
    phone_match = _PHONE_RE.search(text or "")
    email_match = _EMAIL_RE.search(text or "")
    phone = phone_match.group(1).strip() if phone_match else ""
    email = email_match.group(0) if email_match else None
    return phone, email

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.models.client import Client
from app.database.models.contract import Contract
from app.database.session import get_session
from app.services import audit_service, signing_service
from app.services.contract_service import now_almaty
from app.utils.masking import mask_iin, mask_phone

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

PAYMENT_LABELS = {
    "prepayment": "Оплата до начала работы",
    "after_result": "Оплата после достижения результата",
    "split": "Оплата частями",
    "already_paid": "Оплачено",
    "custom": "Индивидуальный порядок оплаты",
}


def _format_amount(amount) -> str:
    try:
        value = int(amount or 0)
    except (TypeError, ValueError):
        value = 0
    return f"{value:,}".replace(",", " ") + " ₸"


def _contract_summary(contract: Contract) -> dict[str, str]:
    data = contract.service_data or {}
    return {
        "service": str(data.get("service_type") or "Индивидуальные юридические услуги"),
        "result": str(
            data.get("result_definition")
            or "Конкретный результат и объём действий указаны на первой странице договора"
        ),
        "amount": _format_amount(contract.amount),
        "payment": PAYMENT_LABELS.get(contract.payment_type, "По условиям договора"),
        "period": str(
            data.get("work_period")
            or "До 30 календарных дней для действий Исполнителя; ожидание ответов третьих лиц не включается"
        ),
    }


@router.get("/sign/{contract_id}", response_class=HTMLResponse)
async def show_signing_page(
    contract_id: int,
    token: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    contract = await session.get(Contract, contract_id)
    if contract is None:
        return templates.TemplateResponse(
            request,
            "sign_error.html",
            {"message": "Договор не найден"},
            status_code=404,
        )

    try:
        await signing_service.resolve_signing_token(session, contract_id, token)
    except signing_service.SigningError as exc:
        return templates.TemplateResponse(
            request,
            "sign_error.html",
            {"message": str(exc)},
            status_code=410,
        )

    client = await session.get(Client, contract.client_id)
    assert client is not None, "contract.client_id must reference an existing client"
    settings = get_settings()

    await audit_service.log_action(
        session,
        action="signing_page_opened",
        entity_type="contract",
        entity_id=contract.id,
        details={"contract_version": contract.version},
        ip_address=request.client.host if request.client else None,
    )
    await session.commit()

    return templates.TemplateResponse(
        request,
        "sign.html",
        {
            "contract": contract,
            "client_name": client.full_name,
            "client_iin_masked": mask_iin(client.iin),
            "client_phone_masked": mask_phone(client.phone),
            "token": token,
            "consent_text": signing_service.get_consent_text(),
            "summary": _contract_summary(contract),
            "feedback_reasons": signing_service.SIGNING_FEEDBACK_REASONS,
            "preview_url": f"/sign/{contract.id}/preview?token={token}",
            "payment_recipient": settings.executor_bank_beneficiary,
            "bank_name": settings.executor_bank_name,
            "kaspi_number": settings.executor_kaspi_number,
        },
    )


@router.get("/sign/{contract_id}/preview")
async def preview_contract_pdf(
    contract_id: int,
    token: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    contract = await session.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Договор не найден")
    try:
        await signing_service.resolve_signing_token(session, contract_id, token)
    except signing_service.SigningError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    if not contract.pdf_path:
        raise HTTPException(status_code=404, detail="PDF договора недоступен")

    await audit_service.log_action(
        session,
        action="contract_pdf_previewed",
        entity_type="contract",
        entity_id=contract.id,
        details={"contract_version": contract.version},
        ip_address=request.client.host if request.client else None,
    )
    await session.commit()
    return FileResponse(
        contract.pdf_path,
        filename=f"dogovor_{contract.contract_number}.pdf",
        media_type="application/pdf",
    )


@router.post("/sign/{contract_id}/feedback")
async def submit_signing_feedback(
    contract_id: int,
    request: Request,
    token: str = Form(...),
    reason: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    contract = await session.get(Contract, contract_id)
    if contract is None:
        return JSONResponse({"ok": False, "message": "Договор не найден"}, status_code=404)
    try:
        await signing_service.resolve_signing_token(session, contract_id, token)
        reason_code, reason_label = signing_service.normalize_feedback_reason(reason)
    except signing_service.SigningError as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=400)

    await audit_service.log_action(
        session,
        action="contract_signing_feedback",
        entity_type="contract",
        entity_id=contract.id,
        details={"reason": reason_code, "reason_label": reason_label},
        ip_address=request.client.host if request.client else None,
    )
    await session.commit()
    return JSONResponse({"ok": True, "message": "Спасибо. Ответ сохранён."})


@router.post("/sign/{contract_id}", response_class=HTMLResponse)
async def submit_signature(
    contract_id: int,
    request: Request,
    token: str = Form(...),
    consent: bool = Form(False),
    signature_image: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    contract = await session.get(Contract, contract_id)
    if contract is None:
        return templates.TemplateResponse(
            request,
            "sign_error.html",
            {"message": "Договор не найден"},
            status_code=404,
        )

    try:
        signing_token = await signing_service.resolve_signing_token(session, contract_id, token)
        client_signature = await signing_service.complete_signing(
            session,
            contract=contract,
            token=signing_token,
            signature_data_url=signature_image,
            consent_accepted=consent,
            client_telegram_id=None,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except signing_service.SigningError as exc:
        await audit_service.log_action(
            session,
            action="contract_signing_error",
            entity_type="contract",
            entity_id=contract.id,
            details={"error_type": type(exc).__name__},
            ip_address=request.client.host if request.client else None,
        )
        await session.commit()
        return templates.TemplateResponse(
            request,
            "sign_error.html",
            {"message": str(exc)},
            status_code=400,
        )

    await audit_service.log_action(
        session,
        action="contract_signed",
        entity_type="contract",
        entity_id=contract.id,
        details={"client_signature_id": client_signature.id},
        ip_address=request.client.host if request.client else None,
    )
    await session.commit()

    return templates.TemplateResponse(
        request,
        "sign_success.html",
        {
            "contract_number": contract.contract_number,
            "signed_at": now_almaty().strftime("%d.%m.%Y %H:%M"),
            "download_url": f"/sign/{contract.id}/download?token={token}",
        },
    )


@router.get("/sign/{contract_id}/download")
async def download_signed_pdf(
    contract_id: int,
    token: str,
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    contract = await session.get(Contract, contract_id)
    if contract is None or contract.status != "signed":
        raise HTTPException(status_code=404, detail="Подписанный договор недоступен")
    from sqlalchemy import select

    from app.database.models.signature import SigningToken

    result = await session.execute(select(SigningToken).where(SigningToken.contract_id == contract_id))
    tokens = result.scalars().all()
    from app.core.security import verify_token

    if not any(verify_token(token, item.token_hash) for item in tokens):
        raise HTTPException(status_code=403, detail="Недействительная ссылка")

    assert contract.pdf_path is not None
    return FileResponse(
        contract.pdf_path,
        filename=f"dogovor_{contract.contract_number}.pdf",
        media_type="application/pdf",
    )

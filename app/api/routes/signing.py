from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.client import Client
from app.database.models.contract import Contract
from app.database.session import get_session
from app.services import audit_service, signing_service
from app.services.contract_service import now_almaty
from app.utils.masking import mask_iin, mask_phone

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/sign/{contract_id}", response_class=HTMLResponse)
async def show_signing_page(
    contract_id: int, token: str, request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    contract = await session.get(Contract, contract_id)
    if contract is None:
        return templates.TemplateResponse(
            request, "sign_error.html", {"message": "Договор не найден"}, status_code=404
        )

    try:
        await signing_service.resolve_signing_token(session, contract_id, token)
    except signing_service.SigningError as exc:
        return templates.TemplateResponse(
            request, "sign_error.html", {"message": str(exc)}, status_code=410
        )

    client = await session.get(Client, contract.client_id)
    assert client is not None, "contract.client_id must reference an existing client"
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
        },
    )


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
            request, "sign_error.html", {"message": "Договор не найден"}, status_code=404
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
        return templates.TemplateResponse(
            request, "sign_error.html", {"message": str(exc)}, status_code=400
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
        {"contract_number": contract.contract_number, "signed_at": now_almaty().strftime("%d.%m.%Y %H:%M")},
    )


@router.get("/sign/{contract_id}/download")
async def download_signed_pdf(
    contract_id: int, token: str, session: AsyncSession = Depends(get_session)
) -> FileResponse:
    contract = await session.get(Contract, contract_id)
    if contract is None or contract.status != "signed":
        raise signing_service.SigningError("Подписанный договор недоступен")
    from sqlalchemy import select

    from app.database.models.signature import SigningToken

    result = await session.execute(
        select(SigningToken).where(SigningToken.contract_id == contract_id)
    )
    tokens = result.scalars().all()
    from app.core.security import verify_token

    if not any(verify_token(token, t.token_hash) for t in tokens):
        raise signing_service.TokenInvalidError("Недействительная ссылка")

    assert contract.pdf_path is not None
    return FileResponse(contract.pdf_path, filename=f"dogovor_{contract.contract_number}.pdf")

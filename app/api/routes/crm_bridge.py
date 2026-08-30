from __future__ import annotations

import base64
import binascii
import hmac
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.models.client import Client
from app.database.models.contract import Contract
from app.database.models.user import User
from app.database.session import get_session
from app.schemas.conditions import ContractConditions
from app.schemas.identity import IdentityExtraction
from app.services import contract_service, crm_sync_service
from app.services.contract_import_service import parse_contract_bytes
from app.services.openai_service import OpenAIService

router = APIRouter(prefix="/internal/crm", tags=["crm-internal"])


class ContractImportRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=240)
    mime_type: str = Field(default="", max_length=160)
    data_base64: str = Field(min_length=4, max_length=16_000_000)


class CrmClientInput(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    iin: str = Field(pattern=r"^\d{12}$")
    phone: str = Field(default="", max_length=32)
    address: str = Field(default="", max_length=512)
    document_number: str = Field(default="", max_length=64)
    birth_date: str | None = Field(default=None, pattern=r"^\d{2}\.\d{2}\.\d{4}$")


class ContractCreateRequest(BaseModel):
    client: CrmClientInput
    service: str = Field(min_length=3, max_length=2000)
    service_details: list[str] = Field(default_factory=list, max_length=50)
    amount: int = Field(gt=0, le=1_000_000_000)
    payment_type: Literal["prepayment", "after_result", "split", "already_paid", "custom"] = "prepayment"
    first_payment: int | None = Field(default=None, ge=0, le=1_000_000_000)
    second_payment: int | None = Field(default=None, ge=0, le=1_000_000_000)
    work_period: str | None = Field(default=None, max_length=500)
    result_definition: str | None = Field(default=None, max_length=4000)
    subject_paragraph: str | None = Field(default=None, max_length=6000)
    actions_paragraph: str | None = Field(default=None, max_length=6000)


def _require_crm_key(x_crm_integration_key: str = Header(default="")) -> None:
    expected = get_settings().crm_integration_key.strip()
    if len(expected) < 24 or not hmac.compare_digest(x_crm_integration_key, expected):
        raise HTTPException(status_code=401, detail="UNAUTHORIZED")


async def _resolve_crm_manager(session: AsyncSession) -> User:
    settings = get_settings()
    ids = list(settings.superadmin_ids)
    if not ids:
        raise HTTPException(status_code=503, detail="CRM_MANAGER_NOT_CONFIGURED")
    result = await session.execute(
        select(User)
        .where(User.telegram_id.in_(ids), User.is_active.is_(True))
        .order_by(User.id.asc())
    )
    manager = result.scalars().first()
    if manager is None:
        raise HTTPException(status_code=503, detail="CRM_MANAGER_NOT_FOUND")
    return manager


async def _get_or_create_client(session: AsyncSession, data: CrmClientInput) -> Client:
    result = await session.execute(
        select(Client).where(Client.iin == data.iin).order_by(Client.id.desc())
    )
    client = result.scalars().first()
    if client is not None:
        client.full_name = data.name
        if data.phone:
            client.phone = data.phone
        if data.address:
            client.address = data.address
        if data.document_number:
            client.document_number = data.document_number
        await session.flush()
        return client

    identity = IdentityExtraction(
        full_name=data.name,
        iin=data.iin,
        birth_date=data.birth_date,
        document_number=data.document_number or None,
    )
    return await contract_service.create_client_from_identity(
        session,
        identity,
        phone=data.phone or None,
        address=data.address or None,
    )


@router.post("/create-contract", dependencies=[Depends(_require_crm_key)])
async def create_contract(
    payload: ContractCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    manager = await _resolve_crm_manager(session)
    try:
        client = await _get_or_create_client(session, payload.client)
        conditions = ContractConditions(
            service_type=payload.service,
            service_details=payload.service_details,
            amount_kzt=payload.amount,
            payment_type=payload.payment_type,
            first_payment_kzt=payload.first_payment,
            second_payment_kzt=payload.second_payment,
            work_period=payload.work_period,
            client_phone=payload.client.phone or None,
            result_definition=payload.result_definition,
            subject_paragraph=payload.subject_paragraph,
            actions_paragraph=payload.actions_paragraph,
        )
        conditions.template_code = OpenAIService.suggest_template(conditions)
        if not conditions.result_definition:
            conditions.result_definition = OpenAIService.suggest_result_definition(conditions)
        if not conditions.subject_paragraph and not conditions.actions_paragraph:
            await contract_service.draft_narrative_for_conditions(OpenAIService(), conditions)

        contract = await contract_service.create_draft_contract(
            session,
            manager_id=manager.id,
            client=client,
            conditions=conditions,
            template_code=conditions.template_code,
        )
        await contract_service.approve_contract_documents(
            session,
            contract,
            client,
            approved_by_id=manager.id,
        )
        await session.commit()
        await session.refresh(contract)
        await session.refresh(client)

        # The approval path already performs a best-effort delivery. Repeat after the DB
        # commit so the CRM also receives a committed state; externalContractId makes this
        # retry idempotent.
        await crm_sync_service.sync_contract_to_crm(contract, client)
        return {
            "ok": True,
            "contract": crm_sync_service.build_contract_payload(contract, client),
        }
    except HTTPException:
        await session.rollback()
        raise
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=500, detail="CONTRACT_CREATE_FAILED") from exc


@router.post("/parse-contract", dependencies=[Depends(_require_crm_key)])
async def parse_contract(payload: ContractImportRequest) -> dict:
    try:
        data = base64.b64decode(payload.data_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="BAD_BASE64") from exc
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="FILE_TOO_LARGE")
    try:
        parsed = parse_contract_bytes(data, filename=payload.filename, mime_type=payload.mime_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "contract": parsed}


@router.get("/contracts/{contract_id}/file", dependencies=[Depends(_require_crm_key)])
async def contract_file(
    contract_id: int,
    kind: str = Query(default="pdf", pattern="^(pdf|docx)$"),
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    contract = await session.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="CONTRACT_NOT_FOUND")
    raw_path = contract.pdf_path if kind == "pdf" else contract.docx_path
    if not raw_path:
        raise HTTPException(status_code=404, detail="FILE_NOT_FOUND")
    path = Path(raw_path).resolve()
    settings = get_settings()
    documents_root = settings.documents_dir.resolve()
    try:
        path.relative_to(documents_root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="FILE_OUTSIDE_STORAGE") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="FILE_NOT_FOUND")
    media_type = (
        "application/pdf"
        if kind == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return FileResponse(
        path,
        media_type=media_type,
        filename=f"dogovor-{contract.contract_number}.{kind}",
    )

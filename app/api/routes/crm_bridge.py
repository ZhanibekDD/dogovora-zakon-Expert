from __future__ import annotations

import base64
import binascii
import hmac
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.models.contract import Contract
from app.database.session import get_session
from app.services.contract_import_service import parse_contract_bytes

router = APIRouter(prefix="/internal/crm", tags=["crm-internal"])


class ContractImportRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=240)
    mime_type: str = Field(default="", max_length=160)
    data_base64: str = Field(min_length=4, max_length=16_000_000)


def _require_crm_key(x_crm_integration_key: str = Header(default="")) -> None:
    expected = get_settings().crm_integration_key.strip()
    if len(expected) < 24 or not hmac.compare_digest(x_crm_integration_key, expected):
        raise HTTPException(status_code=401, detail="UNAUTHORIZED")


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

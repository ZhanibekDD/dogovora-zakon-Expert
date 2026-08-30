from __future__ import annotations

import asyncio
import datetime
import json
import urllib.error
import urllib.request
from decimal import Decimal
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.models.client import Client
from app.database.models.contract import Contract

logger = get_logger(__name__)


def _json_number(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _iso_date(value: datetime.datetime | datetime.date | None) -> str:
    if value is None:
        return datetime.date.today().isoformat()
    if isinstance(value, datetime.datetime):
        return value.date().isoformat()
    return value.isoformat()


def build_contract_payload(contract: Contract, client: Client) -> dict[str, Any]:
    service_data = dict(contract.service_data or {})
    phone = str(service_data.get("client_phone") or client.phone or "").strip()
    service = str(service_data.get("service_type") or "").strip()

    return {
        "source": "dogovora-zakon-Expert",
        "externalContractId": f"dogovora:{contract.id}",
        "generatorContractId": contract.id,
        "number": str(contract.contract_number),
        "title": "Договор оказания услуг",
        "date": _iso_date(contract.approved_at or contract.created_at),
        "amount": _json_number(contract.amount),
        "currency": contract.currency or "KZT",
        "service": service,
        "serviceDetails": list(service_data.get("service_details") or []),
        "paymentType": contract.payment_type or "",
        "paymentStatus": contract.payment_status or "",
        "contractStatus": contract.status or "",
        "documentSha256": contract.document_sha256 or "",
        "hasPdf": bool(contract.pdf_path),
        "hasDocx": bool(contract.docx_path),
        "client": {
            "externalClientId": f"dogovora:{client.id}",
            "name": client.full_name or "",
            "iin": client.iin or "",
            "phone": phone,
            "address": client.address or "",
            "documentNumber": client.document_number or "",
        },
    }


def _post_json(url: str, integration_key: str, payload: dict[str, Any], timeout: float) -> int:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "X-CRM-Integration-Key": integration_key,
            "User-Agent": "ZakonExpert-Contract-Generator/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        response.read(4096)
        return int(response.status)


async def sync_contract_to_crm(contract: Contract, client: Client) -> bool:
    """Best-effort CRM delivery.

    Contract creation must never fail because CRM is temporarily unavailable. The CRM endpoint
    is idempotent by externalContractId, so retries/reissues are safe.
    """

    settings = get_settings()
    url = settings.crm_sync_url.strip()
    integration_key = settings.crm_integration_key.strip()
    if not url or not integration_key:
        return False

    payload = build_contract_payload(contract, client)
    timeout = float(settings.crm_sync_timeout_seconds)
    try:
        status = await asyncio.wait_for(
            asyncio.to_thread(_post_json, url, integration_key, payload, timeout),
            timeout=timeout + 1.0,
        )
        if 200 <= status < 300:
            return True
        logger.warning("crm_contract_sync_non_success", status=status, contract_id=contract.id)
    except (TimeoutError, urllib.error.URLError, OSError, ValueError) as exc:
        logger.warning(
            "crm_contract_sync_failed",
            contract_id=contract.id,
            error=type(exc).__name__,
        )
    return False

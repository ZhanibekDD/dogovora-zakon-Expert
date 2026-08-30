from __future__ import annotations

import asyncio
import json
import os
import socket
import urllib.error
import urllib.request
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.models.client import Client
from app.database.models.contract import Contract
from app.database.models.user import User
from app.database.session import session_scope
from app.schemas.conditions import ContractConditions
from app.schemas.identity import IdentityExtraction
from app.services import contract_service, crm_sync_service
from app.services.openai_service import OpenAIService

logger = get_logger(__name__)


def _jobs_base_url() -> str:
    settings = get_settings()
    sync_url = settings.crm_sync_url.strip().rstrip("/")
    suffix = "/api/crm/integrations/contracts"
    if sync_url.endswith(suffix):
        return sync_url[: -len(suffix)] + "/api/crm/integrations/generator/jobs"
    if sync_url.startswith("https://") or sync_url.startswith("http://"):
        parts = sync_url.split("/", 3)
        return "/".join(parts[:3]) + "/api/crm/integrations/generator/jobs"
    return ""


def _worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _request_json(url: str, payload: dict[str, Any], *, timeout: float = 15.0) -> dict[str, Any]:
    settings = get_settings()
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "X-CRM-Integration-Key": settings.crm_integration_key.strip(),
            "User-Agent": "ZakonExpert-Contract-Generator/CRM-Pull-Worker",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        raw = response.read(1024 * 1024)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))


async def _post(url: str, payload: dict[str, Any], timeout: float = 15.0) -> dict[str, Any]:
    return await asyncio.to_thread(_request_json, url, payload, timeout=timeout)


async def _resolve_manager(session) -> User:
    settings = get_settings()
    ids = list(settings.superadmin_ids)
    if not ids:
        raise RuntimeError("CRM_MANAGER_NOT_CONFIGURED")
    result = await session.execute(
        select(User)
        .where(User.telegram_id.in_(ids), User.is_active.is_(True))
        .order_by(User.id.asc())
    )
    manager = result.scalars().first()
    if manager is None:
        raise RuntimeError("CRM_MANAGER_NOT_FOUND")
    return manager


async def _get_or_create_client(session, payload: dict[str, Any]) -> Client:
    iin = str(payload.get("iin") or "").strip()
    result = await session.execute(select(Client).where(Client.iin == iin).order_by(Client.id.desc()))
    client = result.scalars().first()
    if client is not None:
        client.full_name = str(payload.get("name") or client.full_name)
        phone = str(payload.get("phone") or "").strip()
        address = str(payload.get("address") or "").strip()
        document_number = str(payload.get("documentNumber") or "").strip()
        if phone:
            client.phone = phone
        if address:
            client.address = address
        if document_number:
            client.document_number = document_number
        await session.flush()
        return client

    identity = IdentityExtraction(
        full_name=str(payload.get("name") or ""),
        iin=iin,
        document_number=str(payload.get("documentNumber") or "").strip() or None,
    )
    return await contract_service.create_client_from_identity(
        session,
        identity,
        phone=str(payload.get("phone") or "").strip() or None,
        address=str(payload.get("address") or "").strip() or None,
    )


async def _find_existing_job_contract(session, job_id: str) -> tuple[Contract, Client] | None:
    # No schema migration is needed: the CRM job id is stored inside result_data. Scanning
    # recent contracts also works in both PostgreSQL and SQLite test environments.
    result = await session.execute(select(Contract).order_by(Contract.id.desc()).limit(1500))
    for contract in result.scalars():
        if str((contract.result_data or {}).get("crm_job_id") or "") == job_id:
            client = await session.get(Client, contract.client_id)
            if client is not None:
                return contract, client
    return None


async def _create_contract_for_job(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    async with session_scope() as session:
        existing = await _find_existing_job_contract(session, job_id)
        if existing is not None:
            contract, client = existing
            return crm_sync_service.build_contract_payload(contract, client)

        manager = await _resolve_manager(session)
        client = await _get_or_create_client(session, payload)
        payment_type = str(payload.get("paymentType") or "prepayment")
        conditions = ContractConditions(
            service_type=str(payload.get("service") or "").strip(),
            service_details=list(payload.get("serviceDetails") or []),
            amount_kzt=int(payload.get("amount") or 0),
            payment_type=payment_type,
            first_payment_kzt=payload.get("firstPayment"),
            second_payment_kzt=payload.get("secondPayment"),
            work_period=str(payload.get("workPeriod") or "").strip() or None,
            client_phone=str(payload.get("phone") or "").strip() or None,
            result_definition=str(payload.get("resultDefinition") or "").strip() or None,
        )
        conditions.template_code = OpenAIService.suggest_template(conditions)
        if not conditions.result_definition:
            conditions.result_definition = OpenAIService.suggest_result_definition(conditions)
        await contract_service.draft_narrative_for_conditions(OpenAIService(), conditions)

        contract = await contract_service.create_draft_contract(
            session,
            manager_id=manager.id,
            client=client,
            conditions=conditions,
            template_code=conditions.template_code,
        )
        contract.result_data = {**(contract.result_data or {}), "crm_job_id": job_id}
        await contract_service.approve_contract_documents(
            session,
            contract,
            client,
            approved_by_id=manager.id,
        )
        await session.flush()
        payload_out = crm_sync_service.build_contract_payload(contract, client)
    return payload_out


async def _claim(base: str, worker_id: str) -> dict[str, Any] | None:
    response = await _post(f"{base}/claim", {"workerId": worker_id}, timeout=12.0)
    job = response.get("job")
    return job if isinstance(job, dict) else None


async def _complete(base: str, job_id: str, contract_payload: dict[str, Any]) -> None:
    await _post(f"{base}/{job_id}/complete", {"contract": contract_payload}, timeout=20.0)


async def _fail(base: str, job_id: str, error: str) -> None:
    try:
        await _post(f"{base}/{job_id}/fail", {"error": error[:1000]}, timeout=10.0)
    except Exception:  # noqa: BLE001
        logger.warning("crm_job_fail_report_failed", job_id=job_id)


async def run_crm_pull_worker() -> None:
    settings = get_settings()
    base = _jobs_base_url()
    key = settings.crm_integration_key.strip()
    if not base or len(key) < 24:
        logger.info("crm_pull_worker_disabled")
        return

    interval = max(1.0, min(30.0, float(os.getenv("CRM_PULL_INTERVAL_SECONDS", "3"))))
    worker_id = _worker_id()
    logger.info("crm_pull_worker_started", worker_id=worker_id, base_url=base)

    while True:
        try:
            job = await _claim(base, worker_id)
            if not job:
                await asyncio.sleep(interval)
                continue
            job_id = str(job.get("id") or "").strip()
            payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
            if not job_id:
                await asyncio.sleep(interval)
                continue
            logger.info("crm_job_claimed", job_id=job_id, attempt=job.get("attempts"))
            try:
                contract_payload = await _create_contract_for_job(job_id, payload)
                await _complete(base, job_id, contract_payload)
                logger.info("crm_job_completed", job_id=job_id, number=contract_payload.get("number"))
            except Exception as exc:  # noqa: BLE001
                logger.exception("crm_job_generation_failed", job_id=job_id)
                await _fail(base, job_id, f"{type(exc).__name__}: {exc}")
        except asyncio.CancelledError:
            raise
        except (TimeoutError, urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            logger.warning("crm_pull_unreachable", error=type(exc).__name__)
            await asyncio.sleep(max(interval, 5.0))
        except Exception:  # noqa: BLE001
            logger.exception("crm_pull_worker_error")
            await asyncio.sleep(max(interval, 5.0))

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.models.contract import Contract
from app.database.session import session_scope
from app.services.crm_sync_service import sync_contract_to_crm

logger = get_logger(__name__)

MARKER_NAME = ".crm-historical-backfill-v1.json"


def _enabled() -> bool:
    raw = os.getenv("CRM_BACKFILL_EXISTING_CONTRACTS", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def marker_path() -> Path:
    return get_settings().storage_path / MARKER_NAME


async def backfill_existing_contracts_once() -> dict[str, int | bool]:
    """Project all contracts already present in PostgreSQL into CRM exactly once.

    The CRM endpoint itself is idempotent by ``externalContractId`` so a retry is safe. The
    marker is written only when every row was delivered successfully. New contracts continue
    to use the normal real-time sync path and therefore do not depend on this backfill.
    """

    settings = get_settings()
    marker = marker_path()
    if not _enabled():
        logger.info("crm_historical_backfill_disabled")
        return {"skipped": True, "total": 0, "synced": 0, "failed": 0}
    if not settings.crm_sync_url.strip() or len(settings.crm_integration_key.strip()) < 24:
        logger.info("crm_historical_backfill_not_configured")
        return {"skipped": True, "total": 0, "synced": 0, "failed": 0}
    if marker.exists():
        logger.info("crm_historical_backfill_already_done", marker=str(marker))
        return {"skipped": True, "total": 0, "synced": 0, "failed": 0}

    async with session_scope() as session:
        result = await session.execute(select(Contract).order_by(Contract.id.asc()))
        contracts = list(result.scalars().unique())
        total = len(contracts)
        synced = 0
        failed = 0
        logger.info("crm_historical_backfill_started", total=total)

        for index, contract in enumerate(contracts, start=1):
            try:
                ok = await sync_contract_to_crm(contract, contract.client)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "crm_historical_backfill_row_error",
                    contract_id=contract.id,
                    contract_number=contract.contract_number,
                )
                ok = False
            if ok:
                synced += 1
            else:
                failed += 1
            if index % 100 == 0 or index == total:
                logger.info(
                    "crm_historical_backfill_progress",
                    processed=index,
                    total=total,
                    synced=synced,
                    failed=failed,
                )
            await asyncio.sleep(0.05)

    if failed == 0:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps({"version": 1, "total": total, "synced": synced}, ensure_ascii=False),
            encoding="utf-8",
        )
        with contextlib.suppress(OSError):
            marker.chmod(0o600)
        logger.info("crm_historical_backfill_completed", total=total, synced=synced)
    else:
        logger.warning("crm_historical_backfill_incomplete", total=total, synced=synced, failed=failed)

    return {"skipped": False, "total": total, "synced": synced, "failed": failed}

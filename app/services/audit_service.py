from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database.models.audit import AuditLog
from app.utils.masking import mask_text

logger = get_logger(__name__)


async def log_action(
    session: AsyncSession,
    *,
    action: str,
    user_id: int | None = None,
    telegram_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
) -> None:
    """Persist an audit trail entry. `details` is masked before both storage and stdout logging
    so IIN/phone values never leak in plaintext, matching the project's PII-handling rules."""
    safe_details = {k: (mask_text(v) if isinstance(v, str) else v) for k, v in (details or {}).items()}
    entry = AuditLog(
        user_id=user_id,
        telegram_id=telegram_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=safe_details,
        ip_address=ip_address,
    )
    session.add(entry)
    await session.flush()
    logger.info(
        "audit",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        telegram_id=telegram_id,
    )

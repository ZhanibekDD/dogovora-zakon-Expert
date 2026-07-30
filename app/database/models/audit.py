from __future__ import annotations

from sqlalchemy import JSON, BigInteger, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin

JSONType = JSON().with_variant(JSONB(), "postgresql")


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(nullable=True)
    details: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

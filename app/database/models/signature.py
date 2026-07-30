from __future__ import annotations

import datetime

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class SignatureAsset(Base, TimestampMixin):
    """Executor's own signature/stamp PNGs. Never exposed to end users directly."""

    __tablename__ = "signature_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # signature | stamp
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class SigningToken(Base, TimestampMixin):
    __tablename__ = "signing_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime.datetime] = mapped_column(nullable=False)
    used_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class ClientSignature(Base, TimestampMixin):
    """Records a client's simple electronic signature act. Never auto-generated."""

    __tablename__ = "client_signatures"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    signature_image_path: Mapped[str] = mapped_column(String(512), nullable=False)
    consent_text: Mapped[str] = mapped_column(String(2000), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    original_pdf_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    signed_pdf_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_version: Mapped[int] = mapped_column(nullable=False)
    signed_at: Mapped[datetime.datetime] = mapped_column(nullable=False)

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.database.models.client import Client

JSONType = JSON().with_variant(JSONB(), "postgresql")


class ContractTemplate(Base, TimestampMixin):
    __tablename__ = "contract_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    docx_path: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class ContractCounter(Base):
    __tablename__ = "contract_counters"

    id: Mapped[int] = mapped_column(primary_key=True)
    current_number: Mapped[int] = mapped_column(nullable=False, default=0)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False
    )


class ContractCounterLog(Base, TimestampMixin):
    __tablename__ = "contract_counter_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    old_value: Mapped[int] = mapped_column(nullable=False)
    new_value: Mapped[int] = mapped_column(nullable=False)
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    changed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Contract(Base, TimestampMixin):
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_number: Mapped[int] = mapped_column(unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("contract_templates.id"), nullable=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    manager_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="KZT")
    payment_type: Mapped[str] = mapped_column(String(32), nullable=False, default="prepayment")
    payment_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")

    service_data: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    result_data: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    approved_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)
    signed_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)

    docx_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    document_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(default=1, nullable=False)

    client: Mapped[Client] = relationship(lazy="joined")  # noqa: F821
    template: Mapped[ContractTemplate | None] = relationship(lazy="joined")
    versions: Mapped[list[ContractVersion]] = relationship(
        back_populates="contract", order_by="ContractVersion.version"
    )


class ContractVersion(Base, TimestampMixin):
    __tablename__ = "contract_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    service_data: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    result_data: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    docx_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    contract: Mapped[Contract] = relationship(back_populates="versions")

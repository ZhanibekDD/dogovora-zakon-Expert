from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"), nullable=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

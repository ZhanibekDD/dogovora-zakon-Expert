from __future__ import annotations

import datetime

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class Client(Base, TimestampMixin):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    middle_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    iin: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    birth_date: Mapped[datetime.date | None] = mapped_column(nullable=True)
    document_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    updated_at: Mapped[datetime.datetime | None] = mapped_column(
        nullable=True, onupdate=datetime.datetime.utcnow
    )

from __future__ import annotations

import datetime

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), nullable=False)
    stage_name: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    due_date: Mapped[datetime.date | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    paid_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)

from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin

JSONType = JSON().with_variant(JSONB(), "postgresql")


class Setting(Base, TimestampMixin):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    value: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

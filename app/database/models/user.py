from __future__ import annotations

import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    role: Mapped[Role] = relationship(lazy="joined")
    employee: Mapped[Employee | None] = relationship(
        back_populates="user", uselist=False, foreign_keys="Employee.user_id"
    )


class Employee(Base, TimestampMixin):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    added_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    blocked_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    blocked_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)

    user: Mapped[User] = relationship(back_populates="employee", foreign_keys=[user_id])

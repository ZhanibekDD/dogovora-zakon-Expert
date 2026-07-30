"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-13

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True, unique=True),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])

    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("added_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("blocked_reason", sa.String(255), nullable=True),
        sa.Column("blocked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("last_name", sa.String(128), nullable=True),
        sa.Column("first_name", sa.String(128), nullable=True),
        sa.Column("middle_name", sa.String(128), nullable=True),
        sa.Column("iin", sa.String(12), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("document_number", sa.String(64), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("address", sa.String(512), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_clients_iin", "clients", ["iin"])
    op.create_index("ix_clients_telegram_id", "clients", ["telegram_id"])

    op.create_table(
        "contract_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("docx_path", sa.String(512), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_contract_templates_code", "contract_templates", ["code"])

    op.create_table(
        "contract_counters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("current_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "contract_counter_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("old_value", sa.Integer(), nullable=False),
        sa.Column("new_value", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(512), nullable=False),
        sa.Column("changed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "contracts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contract_number", sa.Integer(), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("contract_templates.id"), nullable=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("manager_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="KZT"),
        sa.Column("payment_type", sa.String(32), nullable=False, server_default="prepayment"),
        sa.Column("payment_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("service_data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("result_data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("signed_at", sa.DateTime(), nullable=True),
        sa.Column("docx_path", sa.String(512), nullable=True),
        sa.Column("pdf_path", sa.String(512), nullable=True),
        sa.Column("document_sha256", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_contracts_contract_number", "contracts", ["contract_number"])
    op.create_index("ix_contracts_status", "contracts", ["status"])

    op.create_table(
        "contract_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("service_data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("result_data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("docx_path", sa.String(512), nullable=True),
        sa.Column("pdf_path", sa.String(512), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id"), nullable=False),
        sa.Column("stage_name", sa.String(128), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id"), nullable=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "signature_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "signing_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_signing_tokens_token_hash", "signing_tokens", ["token_hash"])

    op.create_table(
        "client_signatures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id"), nullable=False),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("signature_image_path", sa.String(512), nullable=False),
        sa.Column("consent_text", sa.String(2000), nullable=False),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("original_pdf_sha256", sa.String(64), nullable=False),
        sa.Column("signed_pdf_sha256", sa.String(64), nullable=False),
        sa.Column("contract_version", sa.Integer(), nullable=False),
        sa.Column("signed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])

    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(128), nullable=False, unique=True),
        sa.Column("value", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.bulk_insert(
        sa.table(
            "roles",
            sa.column("id", sa.Integer),
            sa.column("code", sa.String),
            sa.column("name", sa.String),
        ),
        [
            {"id": 1, "code": "superadmin", "name": "Супер-администратор"},
            {"id": 2, "code": "admin", "name": "Администратор"},
            {"id": 3, "code": "manager", "name": "Менеджер"},
            {"id": 4, "code": "client", "name": "Клиент"},
        ],
    )


def downgrade() -> None:
    op.drop_table("settings")
    op.drop_table("audit_logs")
    op.drop_table("client_signatures")
    op.drop_table("signing_tokens")
    op.drop_table("signature_assets")
    op.drop_table("documents")
    op.drop_table("payments")
    op.drop_table("contract_versions")
    op.drop_table("contracts")
    op.drop_table("contract_counter_logs")
    op.drop_table("contract_counters")
    op.drop_table("contract_templates")
    op.drop_table("clients")
    op.drop_table("employees")
    op.drop_table("users")
    op.drop_table("roles")

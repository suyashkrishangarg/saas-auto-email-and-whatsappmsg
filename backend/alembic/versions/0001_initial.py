"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-07
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.models.base import GUID

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

user_role = sa.Enum("SUPER_ADMIN", "CONSULTANT", name="user_role")
user_auth_method = sa.Enum("OAUTH", "FORWARDING", "BOTH", name="user_auth_method")
notice_status = sa.Enum("PROCESSED", "UNMATCHED", "FAILED", name="notice_status")
wa_recipient = sa.Enum("CONSULTANT", "CLIENT", name="whatsapp_recipient_type")
wa_status = sa.Enum("SENT", "FAILED", name="whatsapp_delivery_status")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("full_name", sa.String(200), nullable=True),
        sa.Column("role", user_role, nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("auth_method", user_auth_method, nullable=False),
        sa.Column("forwarding_alias", sa.String(320), nullable=True),
        sa.Column("forwarding_verification_code", sa.String(16), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_forwarding_alias", "users", ["forwarding_alias"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_is_active", "users", ["is_active"])

    op.create_table(
        "google_credentials",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("user_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("history_id", sa.String(64), nullable=True),
        sa.Column("watch_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mailbox_email", sa.String(320), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
    )

    op.create_table(
        "clients",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("consultant_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("gstin", sa.String(15), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("consultant_id", "gstin", name="uq_client_consultant_gstin"),
    )
    op.create_index("ix_clients_gstin", "clients", ["gstin"])
    op.create_index("ix_clients_consultant_id", "clients", ["consultant_id"])

    op.create_table(
        "notices",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("consultant_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", GUID(), sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("raw_subject", sa.String(500), nullable=True),
        sa.Column("sender", sa.String(320), nullable=True),
        sa.Column("extracted_gstin", sa.String(32), nullable=True),
        sa.Column("is_official_notice", sa.Boolean(), nullable=True),
        sa.Column("notice_form", sa.String(50), nullable=True),
        sa.Column("financial_year", sa.String(20), nullable=True),
        sa.Column("tax_period", sa.String(30), nullable=True),
        sa.Column("demand_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", notice_status, nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("processing_latency_ms", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notices_consultant_id", "notices", ["consultant_id"])
    op.create_index("ix_notices_client_id", "notices", ["client_id"])
    op.create_index("ix_notices_extracted_gstin", "notices", ["extracted_gstin"])
    op.create_index("ix_notices_status", "notices", ["status"])
    op.create_index("ix_notices_consultant_created", "notices", ["consultant_id", "created_at"])

    op.create_table(
        "whatsapp_logs",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("notice_id", GUID(), sa.ForeignKey("notices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient_type", wa_recipient, nullable=False),
        sa.Column("recipient_phone", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(32), nullable=True),
        sa.Column("message_id", sa.String(128), nullable=True),
        sa.Column("status", wa_status, nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_whatsapp_logs_notice_id", "whatsapp_logs", ["notice_id"])

    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("system_settings")
    op.drop_index("ix_whatsapp_logs_notice_id", table_name="whatsapp_logs")
    op.drop_table("whatsapp_logs")
    op.drop_index("ix_notices_consultant_created", table_name="notices")
    op.drop_index("ix_notices_status", table_name="notices")
    op.drop_index("ix_notices_extracted_gstin", table_name="notices")
    op.drop_index("ix_notices_client_id", table_name="notices")
    op.drop_index("ix_notices_consultant_id", table_name="notices")
    op.drop_table("notices")
    op.drop_index("ix_clients_consultant_id", table_name="clients")
    op.drop_index("ix_clients_gstin", table_name="clients")
    op.drop_table("clients")
    op.drop_table("google_credentials")
    op.drop_index("ix_users_is_active", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_forwarding_alias", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    wa_status.drop(op.get_bind(), checkfirst=True)
    wa_recipient.drop(op.get_bind(), checkfirst=True)
    notice_status.drop(op.get_bind(), checkfirst=True)
    user_auth_method.drop(op.get_bind(), checkfirst=True)
    user_role.drop(op.get_bind(), checkfirst=True)

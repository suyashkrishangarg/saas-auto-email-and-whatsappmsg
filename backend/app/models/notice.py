from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, GUID, UUIDPk

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.user import User
    from app.models.whatsapp_log import WhatsAppLog


class NoticeStatus(str, enum.Enum):
    PROCESSED = "PROCESSED"      # matched a client, alerts dispatched
    UNMATCHED = "UNMATCHED"      # confirmed notice, no client mapped yet
    FAILED = "FAILED"            # pipeline error


class Notice(UUIDPk, Base):
    __tablename__ = "notices"
    __table_args__ = (
        Index("ix_notices_consultant_created", "consultant_id", "created_at"),
        Index("ix_notices_status", "status"),
    )

    consultant_id: Mapped[object] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id: Mapped[Optional[object]] = mapped_column(
        GUID(), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True
    )

    raw_subject: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    sender: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    extracted_gstin: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)

    # AI-extracted structured fields (single LLM call)
    is_official_notice: Mapped[Optional[bool]] = mapped_column(nullable=True)
    notice_form: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    financial_year: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    tax_period: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    demand_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[NoticeStatus] = mapped_column(
        Enum(NoticeStatus, name="notice_status"), default=NoticeStatus.FAILED, nullable=False
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processing_latency_ms: Mapped[Optional[int]] = mapped_column(nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # GMAIL | FORWARDING
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    consultant: Mapped["User"] = relationship(back_populates="notices")
    client: Mapped[Optional["Client"]] = relationship(back_populates="notices")
    whatsapp_logs: Mapped[list["WhatsAppLog"]] = relationship(
        back_populates="notice", cascade="all, delete-orphan", lazy="selectin"
    )

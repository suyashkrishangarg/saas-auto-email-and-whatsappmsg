from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, GUID, UUIDPk

if TYPE_CHECKING:
    from app.models.notice import Notice


class RecipientType(str, enum.Enum):
    CONSULTANT = "CONSULTANT"
    CLIENT = "CLIENT"


class DeliveryStatus(str, enum.Enum):
    SENT = "SENT"
    FAILED = "FAILED"


class WhatsAppLog(UUIDPk, Base):
    __tablename__ = "whatsapp_logs"

    notice_id: Mapped[object] = mapped_column(
        GUID(), ForeignKey("notices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient_type: Mapped[RecipientType] = mapped_column(
        Enum(RecipientType, name="whatsapp_recipient_type"), nullable=False
    )
    recipient_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    message_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, name="whatsapp_delivery_status"), default=DeliveryStatus.FAILED, nullable=False
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    notice: Mapped["Notice"] = relationship(back_populates="whatsapp_logs")

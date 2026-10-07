from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, GUID, UUIDPk

if TYPE_CHECKING:
    from app.models.user import User


class GoogleCredential(UUIDPk, Base):
    """Encrypted Gmail mailbox connection for users.watch Pub/Sub ingestion."""

    __tablename__ = "google_credentials"

    user_id: Mapped[object] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # short-lived, safe plain
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Fernet-encrypted at rest
    token_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    history_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    watch_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    mailbox_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(32), default="PENDING", nullable=True)

    user: Mapped["User"] = relationship(back_populates="google_credential")

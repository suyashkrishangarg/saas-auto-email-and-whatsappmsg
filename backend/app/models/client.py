from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.models.base import Base, GUID, TimestampMixin, UUIDPk

if TYPE_CHECKING:
    from app.models.notice import Notice
    from app.models.user import User


def _is_alnum_15(v: str) -> bool:
    """Shape check without any regex pattern (product requirement)."""
    if len(v) != 15:
        return False
    for ch in v:
        is_digit = "0" <= ch <= "9"
        is_alpha = ("A" <= ch <= "Z") or ("a" <= ch <= "z")
        if not (is_digit or is_alpha):
            return False
    return True


class Client(UUIDPk, TimestampMixin, Base):
    __tablename__ = "clients"
    __table_args__ = (
        UniqueConstraint("consultant_id", "gstin", name="uq_client_consultant_gstin"),
        Index("ix_clients_gstin", "gstin"),
    )

    consultant_id: Mapped[object] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    gstin: Mapped[str] = mapped_column(String(15), nullable=False)

    consultant: Mapped["User"] = relationship(back_populates="clients")
    notices: Mapped[list["Notice"]] = relationship(back_populates="client")

    @validates("gstin")
    def _normalize_gstin(self, _key: str, value: str) -> str:
        """Uppercase + 15-char shape only. Format correctness is the LLM's job."""
        if value is None:
            raise ValueError("GSTIN is required")
        v = str(value).strip().upper()
        if not _is_alnum_15(v):
            raise ValueError("GSTIN must be exactly 15 alphanumeric characters")
        return v

    @validates("phone")
    def _normalize_phone(self, _key: str, value: Optional[str]) -> Optional[str]:
        """Simple 10-digit check with optional +91 prefix. No regex-based parsing."""
        if value is None or str(value).strip() == "":
            return None
        v = str(value).strip().replace(" ", "").replace("-", "")
        if v.startswith("+91"):
            v = v[3:]
        elif v.startswith("91") and len(v) == 12:
            v = v[2:]
        if not v.isdigit() or len(v) != 10:
            raise ValueError("Phone must be a 10-digit Indian number (optional +91 prefix)")
        return "+91" + v

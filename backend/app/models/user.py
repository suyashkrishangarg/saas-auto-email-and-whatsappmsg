from __future__ import annotations

import enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, GUID, TimestampMixin, UUIDPk

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.google_credential import GoogleCredential
    from app.models.notice import Notice


class Role(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    CONSULTANT = "CONSULTANT"


class AuthMethod(str, enum.Enum):
    OAUTH = "OAUTH"
    FORWARDING = "FORWARDING"
    BOTH = "BOTH"


class User(UUIDPk, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="user_role"), default=Role.CONSULTANT, nullable=False, index=True
    )
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Ingestion channel chosen during onboarding wizard
    auth_method: Mapped[AuthMethod] = mapped_column(
        Enum(AuthMethod, name="user_auth_method"), default=AuthMethod.FORWARDING, nullable=False
    )

    # Unique virtual inbound alias e.g. notices-{uuid}@inbound.ramyaai.tech
    forwarding_alias: Mapped[Optional[str]] = mapped_column(
        String(320), unique=True, index=True, nullable=True
    )
    # 9-digit Gmail forwarding verification code intercepted from inbound webhook
    forwarding_verification_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    google_credential: Mapped[Optional["GoogleCredential"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    clients: Mapped[List["Client"]] = relationship(
        back_populates="consultant", cascade="all, delete-orphan", lazy="selectin"
    )
    notices: Mapped[List["Notice"]] = relationship(
        back_populates="consultant", cascade="all, delete-orphan"
    )

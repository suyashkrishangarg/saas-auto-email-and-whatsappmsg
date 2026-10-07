from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.services.gstin import normalize_gstin, normalize_phone


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------- auth --------------------------------------

def _phone_or_none(v):
    """Accept None/empty; reject non-empty values that fail the simple 10-digit check."""
    if v is None or str(v).strip() == "":
        return None
    p = normalize_phone(v)
    if p is None:
        raise ValueError("Phone must be a 10-digit Indian number (optional +91 prefix)")
    return p


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: Optional[str] = None
    phone: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        return _phone_or_none(v)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class GoogleLoginIn(BaseModel):
    code: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: UUID


class UserOut(ORMModel):
    id: UUID
    email: EmailStr
    full_name: Optional[str]
    role: str
    phone: Optional[str]
    auth_method: str
    forwarding_alias: Optional[str]
    forwarding_verification_code: Optional[str]
    is_active: bool
    created_at: datetime


class OnboardingIn(BaseModel):
    auth_method: str  # OAUTH | FORWARDING | BOTH
    phone: Optional[str] = None

    @field_validator("auth_method")
    @classmethod
    def _method(cls, v):
        v = (v or "").upper()
        if v not in ("OAUTH", "FORWARDING", "BOTH"):
            raise ValueError("auth_method must be OAUTH, FORWARDING or BOTH")
        return v

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        return _phone_or_none(v)


# ------------------------------- clients -----------------------------------

class ClientRowIn(BaseModel):
    consultant_phone: Optional[str] = None
    client_name: str = Field(min_length=1, max_length=200)
    client_phone: Optional[str] = None
    client_gstin: str

    @field_validator("client_gstin")
    @classmethod
    def _gstin(cls, v):
        g = normalize_gstin(v)
        if not g:
            raise ValueError("GSTIN must be exactly 15 uppercase alphanumeric characters")
        return g

    @field_validator("client_phone", "consultant_phone")
    @classmethod
    def _phone(cls, v):
        return _phone_or_none(v)


class ClientBulkIn(BaseModel):
    """Loose rows: validated one-by-one in the endpoint so a single typo
    never blocks the other 49 pasted rows (partial save)."""

    rows: List[dict] = Field(min_length=1, max_length=500)


class ClientOut(ORMModel):
    id: UUID
    consultant_id: UUID
    name: str
    phone: Optional[str]
    gstin: str
    created_at: datetime


class BulkResult(BaseModel):
    created: int
    updated: int
    errors: List[dict] = []


# ------------------------------- notices -----------------------------------

class NoticeOut(ORMModel):
    id: UUID
    consultant_id: UUID
    client_id: Optional[UUID]
    raw_subject: Optional[str]
    sender: Optional[str]
    extracted_gstin: Optional[str]
    is_official_notice: Optional[bool]
    notice_form: Optional[str]
    financial_year: Optional[str]
    tax_period: Optional[str]
    demand_amount: Optional[Decimal]
    due_date: Optional[str]
    summary: Optional[str]
    status: str
    error_message: Optional[str]
    processing_latency_ms: Optional[int]
    source: Optional[str]
    created_at: datetime


class MapNoticeIn(BaseModel):
    client_id: UUID


# ------------------------------- admin -------------------------------------

class SettingIn(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    value: Optional[str] = None
    is_secret: bool = False


class UserAdminUpdate(BaseModel):
    is_active: Optional[bool] = None
    role: Optional[str] = None


class AdminMetrics(BaseModel):
    consultants: int
    active_consultants: int
    suspended: int
    clients: int
    notices_total: int
    notices_24h: int
    unmatched: int
    whatsapp_sent: int
    whatsapp_failed: int
    avg_latency_ms: Optional[float]

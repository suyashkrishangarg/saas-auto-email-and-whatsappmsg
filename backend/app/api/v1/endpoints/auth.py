from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.models.user import AuthMethod, Role, User
from app.schemas import (
    GoogleLoginIn,
    LoginIn,
    OnboardingIn,
    RegisterIn,
    TokenOut,
    UserOut,
)
from app.services import gmail_service

router = APIRouter()


def _alias_for(user_id) -> str:
    return f"notices-{str(user_id)[:8]}@{settings.INBOUND_DOMAIN}"


@router.post("/register", response_model=TokenOut)
async def register(payload: RegisterIn, db: AsyncSession = Depends(get_db)):
    exists = await db.execute(select(User).where(User.email == payload.email.lower()))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
        role=Role.CONSULTANT,
        auth_method=AuthMethod.FORWARDING,
    )
    db.add(user)
    await db.flush()
    user.forwarding_alias = _alias_for(user.id)
    await db.commit()
    token = create_access_token(str(user.id), user.role.value)
    return TokenOut(access_token=token, role=user.role.value, user_id=user.id)


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()
    if user is None or not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account suspended")
    token = create_access_token(str(user.id), user.role.value)
    return TokenOut(access_token=token, role=user.role.value, user_id=user.id)


@router.post("/google", response_model=TokenOut)
async def google_login(payload: GoogleLoginIn, db: AsyncSession = Depends(get_db)):
    """Dashboard SSO: exchange Google authorization code -> app JWT."""
    if not settings.GOOGLE_LOGIN_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Google login not configured")
    try:
        tok = await gmail_service.exchange_code(payload.code)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Google code exchange failed: {exc}") from exc
    try:
        profile = await gmail_service.fetch_profile(tok["access_token"])
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Google profile fetch failed: {exc}") from exc

    email = (profile.get("email") or "").lower()
    if not email:
        raise HTTPException(status_code=400, detail="Google account has no email")
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(email=email, full_name=profile.get("name"), role=Role.CONSULTANT)
        db.add(user)
        await db.flush()
        user.forwarding_alias = _alias_for(user.id)
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account suspended")
    await db.commit()
    token = create_access_token(str(user.id), user.role.value)
    return TokenOut(access_token=token, role=user.role.value, user_id=user.id)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


@router.post("/onboarding", response_model=UserOut)
async def onboarding(
    payload: OnboardingIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Consultant picks their ingestion channel (Gmail OAuth vs forwarding alias)."""
    user.auth_method = AuthMethod(payload.auth_method)
    if payload.phone:
        user.phone = payload.phone
    if not user.forwarding_alias:
        user.forwarding_alias = _alias_for(user.id)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/verification-code", response_model=UserOut)
async def confirm_forwarding_code(
    code: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Consultant confirms the 9-digit Gmail forwarding code surfaced by the wizard."""
    code = code.strip()
    if len(code) != 9 or not code.isdigit():
        raise HTTPException(status_code=400, detail="Verification code must be 9 digits")
    if user.forwarding_verification_code and user.forwarding_verification_code != code:
        raise HTTPException(status_code=400, detail="Code does not match the intercepted code")
    user.forwarding_verification_code = None
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/logout")
async def logout():
    return {"ok": True}

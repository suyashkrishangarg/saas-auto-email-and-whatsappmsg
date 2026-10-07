"""Consultant-facing Gmail OAuth connect + watch lifecycle."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.encryption import encrypt
from app.core.security import require_consultant
from app.models.google_credential import GoogleCredential
from app.models.user import AuthMethod, User
from app.services import gmail_service

router = APIRouter()


@router.get("/connect")
async def oauth_start(user: User = Depends(require_consultant)):
    """Returns the Google consent URL the frontend should redirect to."""
    state = secrets.token_urlsafe(16)
    return {"url": gmail_service.build_consent_url(state), "state": state}


@router.get("/callback")
async def oauth_callback(code: str, state: str, db: AsyncSession = Depends(get_db)):
    """Exchanges code, stores encrypted tokens, starts users.watch.

    NOTE: production would carry a signed state tied to the session; here the
    exchange relies on Google's code flow. Frontend redirects back to dashboard.
    """
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")
    try:
        tok = await gmail_service.exchange_code(code)
        profile = await gmail_service.fetch_profile(tok["access_token"])
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    email = (profile.get("email") or "").lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        # mailbox belongs to nobody yet -> require dashboard login first
        raise HTTPException(
            status_code=404,
            detail="No dashboard account for this mailbox. Login first, then connect.",
        )

    expiry = datetime.now(timezone.utc) + timedelta(seconds=int(tok.get("expires_in", 3600)))
    cred = (
        await db.execute(select(GoogleCredential).where(GoogleCredential.user_id == user.id))
    ).scalar_one_or_none()
    if cred is None:
        cred = GoogleCredential(user_id=user.id)
        db.add(cred)
    cred.access_token = tok.get("access_token")
    cred.refresh_token = encrypt(tok["refresh_token"]) if tok.get("refresh_token") else cred.refresh_token
    cred.token_expiry = expiry
    cred.mailbox_email = email
    cred.status = "PENDING_WATCH"
    await db.flush()

    # Start Gmail watch (needs topic); tolerate missing topic in dev
    watch_error = None
    try:
        w = await gmail_service.start_watch(tok["access_token"])
        cred.history_id = str(w.get("historyId", ""))
        cred.watch_expiry = (
            datetime.now(timezone.utc) + timedelta(seconds=int(w.get("expiration", 604800) ) // 1000)
            if str(w.get("expiration", "")).isdigit()
            else datetime.now(timezone.utc) + timedelta(days=6)
        )
        cred.status = "WATCHING"
    except Exception as exc:
        watch_error = str(exc)
        cred.status = "WATCH_FAILED"

    user.auth_method = (
        AuthMethod.BOTH if user.auth_method != AuthMethod.FORWARDING else AuthMethod.OAUTH
    )
    await db.commit()
    return {
        "ok": True,
        "mailbox": email,
        "watch_status": cred.status,
        "watch_error": watch_error,
        "redirect": f"{settings.FRONTEND_URL}/dashboard?gmail=connected",
    }


@router.post("/renew")
async def renew_watch(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_consultant),
):
    cred = (
        await db.execute(select(GoogleCredential).where(GoogleCredential.user_id == user.id))
    ).scalar_one_or_none()
    if cred is None:
        raise HTTPException(status_code=404, detail="Gmail not connected")
    token = await gmail_service.ensure_fresh_token(cred)
    try:
        w = await gmail_service.start_watch(token)
        cred.history_id = str(w.get("historyId", cred.history_id))
        cred.status = "WATCHING"
    except Exception as exc:
        cred.status = "WATCH_FAILED"
        await db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    cred.last_sync_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True, "status": cred.status}


@router.get("/status")
async def status(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_consultant),
):
    cred = (
        await db.execute(select(GoogleCredential).where(GoogleCredential.user_id == user.id))
    ).scalar_one_or_none()
    return {
        "connected": cred is not None,
        "status": cred.status if cred else None,
        "mailbox": cred.mailbox_email if cred else None,
        "watch_expiry": cred.watch_expiry.isoformat() if cred and cred.watch_expiry else None,
        "last_sync_at": cred.last_sync_at.isoformat() if cred and cred.last_sync_at else None,
    }

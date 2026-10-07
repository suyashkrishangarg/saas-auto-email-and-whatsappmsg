"""Dual ingestion channel webhooks.

1. /ingest/inbound  - SendGrid Inbound Parse / Postmark inbound MTA
2. /ingest/pubsub   - Google Cloud Pub/Sub push for Gmail users.watch

Both push the normalized email payload onto the Redis queue (Celery).
The inbound handler ALSO intercepts Google's 9-digit forwarding verification
email and surfaces the code in the consultant's dashboard banner.
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

logger = logging.getLogger("ingest")
router = APIRouter()

GOOGLE_SENDER_HINTS = ("google.com", "gmail.com")


async def _find_user_by_alias(db: AsyncSession, to_addr: str) -> Optional[User]:
    to_addr = (to_addr or "").strip().lower()
    if not to_addr:
        return None
    result = await db.execute(select(User).where(User.forwarding_alias == to_addr))
    user = result.scalar_one_or_none()
    if user:
        return user
    local = to_addr.split("@")[0]
    if local.startswith("notices-"):
        for u in (await db.execute(select(User))).scalars().all():
            if u.forwarding_alias and u.forwarding_alias.split("@")[0] == local:
                return u
    return None


def _extract_nine_digit_code(subject: str, body: str) -> Optional[str]:
    """Google forwarding confirmation emails carry a 9-digit code.

    Naive digit-scan (deliberately no regex): collect a run of exactly 9 digits.
    """
    for source in (subject or "", body or ""):
        buf = ""
        for ch in source:
            if ch.isdigit():
                buf += ch
                if len(buf) == 9:
                    return buf
                if len(buf) > 9:
                    buf = ""
            else:
                buf = ""
    return None


def _is_google_forwarding_verify(subject: str, sender: str) -> bool:
    s = (subject or "").lower()
    sender_l = (sender or "").lower()
    marker = ("confirmation" in s and "forward" in s) or ("email forwarding" in s)
    return marker and any(h in sender_l for h in GOOGLE_SENDER_HINTS)


def _parse_inbound_form(payload: dict) -> tuple[str, str, str, str, str]:
    to = payload.get("to") or ""
    frm = payload.get("from") or payload.get("from_") or ""
    subject = payload.get("subject") or ""
    text = payload.get("text") or ""
    html = payload.get("html") or ""
    if isinstance(to, list):
        to = to[0] if to else ""
    return str(to), str(frm), str(subject), str(text), str(html)


@router.post("/inbound")
async def inbound_email(
    request: Request, background: BackgroundTasks, db: AsyncSession = Depends(get_db)
):
    """SendGrid Inbound Parse compatible handler (works for Postmark-style posts too)."""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
    else:
        form = await request.form()
        data = {k: form.get(k) for k in ("to", "from", "subject", "text", "html")}
    to, sender, subject, text, html = _parse_inbound_form(data)

    first_recipient = (to.split(",")[0] if to else "").strip().lower()
    user = await _find_user_by_alias(db, first_recipient)

    # ---- Google forwarding verification intercept ----
    if user and _is_google_forwarding_verify(subject, sender):
        code = _extract_nine_digit_code(subject, text or html)
        if code:
            user.forwarding_verification_code = code
            await db.commit()
            logger.info("Intercepted Gmail forwarding code for %s", user.email)
            return {"ok": True, "verification_code": code, "user": str(user.id)}

    if user is None:
        logger.warning("Inbound email for unknown alias: %s", first_recipient)
        return {"ok": True, "note": "alias not found - ignored"}

    from app.workers.runner import enqueue

    return enqueue(
        background,
        "process_notice_email",
        {
            "consultant_id": str(user.id),
            "subject": subject,
            "sender": sender,
            "text": text,
            "html": html,
            "source": "FORWARDING",
            "attachments": [],
        },
    )


@router.post("/pubsub")
async def pubsub_push(
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    x_goog_verification_token: str | None = Header(default=None),
):
    """Google Cloud Pub/Sub push target for Gmail users.watch notifications."""
    if (
        settings.GOOGLE_PUBSUB_VERIFICATION_TOKEN
        and x_goog_verification_token != settings.GOOGLE_PUBSUB_VERIFICATION_TOKEN
    ):
        raise HTTPException(status_code=401, detail="Bad verification token")

    body = await request.json()
    if body.get("message") is None:  # subscription creation retry
        return {"ok": True, "token": settings.GOOGLE_PUBSUB_VERIFICATION_TOKEN}

    msg = body["message"]
    try:
        inner = json.loads(base64.b64decode(msg.get("data", "")).decode("utf-8"))
    except Exception:
        inner = {}
    history_id = str(inner.get("historyId", ""))
    email_address = (inner.get("emailAddress") or "").lower()

    user = None
    if email_address:
        user = (
            await db.execute(select(User).where(User.email == email_address))
        ).scalar_one_or_none()
    if user is None:
        from app.models.google_credential import GoogleCredential

        creds = (await db.execute(select(GoogleCredential))).scalars().all()
        if len(creds) == 1:
            user = await db.get(User, creds[0].user_id)
    if user is None:
        logger.warning("Pub/Sub push could not resolve a user: %s", inner)
        return {"ok": True, "note": "no user"}

    from app.models.google_credential import GoogleCredential

    cred = (
        await db.execute(select(GoogleCredential).where(GoogleCredential.user_id == user.id))
    ).scalar_one_or_none()
    if cred:
        cred.history_id = history_id or cred.history_id
        await db.flush()

    from app.workers.runner import enqueue

    return enqueue(
        background, "process_gmail_message", {"consultant_id": str(user.id), "history_id": history_id}
    )

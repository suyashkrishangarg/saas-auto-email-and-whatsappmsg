"""Gmail OAuth 2.0 + users.watch (Pub/Sub push) helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from app.core.config import settings
from app.core.encryption import decrypt, encrypt

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "openid",
    "email",
]


def build_consent_url(state: str) -> str:
    params = [
        f"client_id={settings.GOOGLE_CLIENT_ID}",
        f"redirect_uri={settings.GOOGLE_REDIRECT_URI}",
        "response_type=code",
        "access_type=offline",
        "prompt=consent",
        "scope=" + "%20".join(SCOPES),
        f"state={state}",
    ]
    return GOOGLE_AUTH_URL + "?" + "&".join(params)


async def exchange_code(code: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(refresh_token: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_profile(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        resp.raise_for_status()
        return resp.json()


async def start_watch(access_token: str) -> dict:
    """users.watch -> returns {historyId, expiration}."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/watch",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"topicName": settings.GOOGLE_PUBSUB_TOPIC, "labelIds": ["INBOX"]},
        )
        resp.raise_for_status()
        return resp.json()


async def stop_watch(access_token: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/stop",
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except Exception:
        pass


async def ensure_fresh_token(credential) -> Optional[str]:
    """Return a valid access token, transparently refreshing if expired."""
    expiry: Optional[datetime] = credential.token_expiry
    stored = decrypt(credential.refresh_token) if credential.refresh_token else None
    if not stored:
        return credential.access_token
    if expiry and expiry > datetime.now(timezone.utc) + timedelta(minutes=5):
        return credential.access_token
    try:
        data = await refresh_access_token(stored)
    except Exception:
        return credential.access_token
    credential.access_token = data.get("access_token", credential.access_token)
    if "expires_in" in data:
        credential.token_expiry = datetime.now(timezone.utc) + timedelta(
            seconds=int(data["expires_in"])
        )
    return credential.access_token


def encrypt_refresh(token: str) -> str:
    return encrypt(token)

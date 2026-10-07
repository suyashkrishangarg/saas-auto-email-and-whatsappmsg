"""Dynamic SettingsService: reads SystemSetting (DB) first, falls back to .env.

Secrets are decrypted transparently on read and encrypted on write, so callers
never see Fernet tokens. Zero-redeployment: super-admin writes propagate on the
next read because the service queries the DB per call (cheap single-row PK lookups).
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as env
from app.core.encryption import decrypt, encrypt
from app.models.system_setting import DEFAULT_SETTINGS, SystemSetting


class SettingsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- raw access ----------
    async def get_raw(self, key: str, default: str = "") -> Optional[str]:
        row = await self.db.get(SystemSetting, key)
        if row is not None and row.value is not None and row.value != "":
            return decrypt(row.value) if row.is_secret else row.value
        # DB miss / empty -> env fallback
        env_val = getattr(env, key.upper().replace(".", "_"), None)
        if env_val:
            return env_val
        seeded = DEFAULT_SETTINGS.get(key)
        if seeded and seeded[0]:
            return seeded[0]
        return default

    async def get(self, key: str, default: str = "") -> str:
        val = await self.get_raw(key, default)
        return default if val is None else val

    async def set(self, key: str, value: Optional[str], is_secret: bool = False) -> None:
        row = await self.db.get(SystemSetting, key)
        stored = encrypt(value) if (is_secret and value) else value
        if row is None:
            self.db.add(SystemSetting(key=key, value=stored, is_secret=is_secret))
        else:
            row.value = stored
            row.is_secret = is_secret
        await self.db.flush()

    # ---------- composite accessors ----------
    @staticmethod
    def _to_float(raw: str, default: float) -> float:
        try:
            return float(str(raw).strip())
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_int(raw: str, default: int) -> int:
        try:
            return int(float(str(raw).strip()))
        except (TypeError, ValueError):
            return default

    async def get_llm_config(self) -> Dict[str, Any]:
        provider = (await self.get("llm.provider")).strip().lower() or None
        model = (await self.get("llm.model")).strip() or None
        system_prompt = (await self.get("llm.system_prompt")).strip() or None
        api_key = ""
        if provider:
            api_key = await self.get(f"llm.api_key.{provider}", "")
            if provider == "custom" and not api_key.strip():
                api_key = await self.get("llm.custom.api_key", "")
        temperature = self._to_float(await self.get("llm.temperature", "0"), 0.0)
        max_tokens = self._to_int(await self.get("llm.max_tokens", "1024"), 1024)
        timeout_s = self._to_float(await self.get("llm.timeout_s", "60"), 60.0)
        max_body_chars = self._to_int(await self.get("llm.max_body_chars", "12000"), 12000)
        custom_base_url = (await self.get("llm.custom.base_url", "")).strip() or None
        custom_model = (await self.get("llm.custom.model", "")).strip() or None
        custom_extra_headers: Dict[str, str] = {}
        raw_headers = (await self.get("llm.custom.extra_headers", "")).strip()
        if raw_headers:
            try:
                import json as _json

                parsed = _json.loads(raw_headers)
                if isinstance(parsed, dict):
                    custom_extra_headers = {str(k): str(v) for k, v in parsed.items()}
            except Exception:  # noqa: BLE001
                custom_extra_headers = {}
        return {
            "provider": provider,
            "model": model,
            "api_key": api_key,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout_s": timeout_s,
            "max_body_chars": max_body_chars,
            "custom_base_url": custom_base_url,
            "custom_model": custom_model,
            "custom_extra_headers": custom_extra_headers,
        }

    async def get_whatsapp_config(self) -> Dict[str, Any]:
        order_raw = await self.get("whatsapp.provider_order", "meta,twilio,gupshup")
        order = [p.strip().lower() for p in order_raw.split(",") if p.strip()]
        return {
            "provider_order": order,
            "meta": {
                "token": await self.get("whatsapp.meta.token", ""),
                "phone_number_id": await self.get("whatsapp.meta.phone_number_id", ""),
                "template_consultant": await self.get("whatsapp.template.consultant", ""),
                "template_client": await self.get("whatsapp.template.client", ""),
            },
            "twilio": {
                "account_sid": await self.get("whatsapp.twilio.account_sid", ""),
                "auth_token": await self.get("whatsapp.twilio.auth_token", ""),
                "from": await self.get("whatsapp.twilio.from", ""),
            },
            "gupshup": {
                "api_key": await self.get("whatsapp.gupshup.api_key", ""),
                "sender": await self.get("whatsapp.gupshup.sender", ""),
            },
        }

    # ---------- management ----------
    async def all(self) -> Dict[str, Dict[str, Any]]:
        rows = (await self.db.execute(select(SystemSetting))).scalars().all()
        out: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            out[r.key] = {
                "value": decrypt(r.value) if (r.is_secret and r.value) else r.value,
                "is_secret": r.is_secret,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                "has_value": bool(r.value),
            }
        for k, (v, s) in DEFAULT_SETTINGS.items():
            if k not in out:
                out[k] = {"value": v, "is_secret": s, "updated_at": None, "has_value": bool(v)}
        return out

    async def seed_defaults(self) -> None:
        for key, (value, is_secret) in DEFAULT_SETTINGS.items():
            if await self.db.get(SystemSetting, key) is None:
                self.db.add(
                    SystemSetting(
                        key=key,
                        value=encrypt(value) if (is_secret and value) else (value or None),
                        is_secret=is_secret,
                    )
                )
        await self.db.flush()


async def get_settings_service(db: AsyncSession) -> SettingsService:
    return SettingsService(db)

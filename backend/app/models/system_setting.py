from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SystemSetting(Base):
    """Dynamic settings engine - zero redeployment.

    Secret values (LLM keys, WhatsApp tokens) are Fernet-encrypted at rest.
    Reads go DB-first; the SettingsService falls back to .env when a key is absent.
    """

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# Canonical keys seeded on startup
DEFAULT_SETTINGS = {
    "llm.provider": ("", False),          # openai | gemini | anthropic | groq | custom
    "llm.model": ("", False),             # e.g. gpt-4o-mini, gemini-1.5-flash
    "llm.api_key.openai": ("", True),
    "llm.api_key.gemini": ("", True),
    "llm.api_key.anthropic": ("", True),
    "llm.api_key.groq": ("", True),
    "llm.api_key.custom": ("", True),
    "llm.system_prompt": ("", False),
    # Custom OpenAI-compatible endpoint (provider = custom)
    "llm.custom.base_url": ("", False),   # e.g. https://xxx/v1 or http://localhost:11434/v1
    "llm.custom.model": ("", False),      # model id served by the custom endpoint
    "llm.custom.api_key": ("", True),     # use llm.api_key.custom (alias, same thing)
    "llm.custom.extra_headers": ("", False),  # optional JSON object of extra HTTP headers
    # Generation tuning (apply everywhere, incl. custom)
    "llm.temperature": ("0", False),
    "llm.max_tokens": ("1024", False),
    "llm.timeout_s": ("60", False),
    "llm.max_body_chars": ("12000", False),
    "whatsapp.meta.token": ("", True),
    "whatsapp.meta.phone_number_id": ("", False),
    "whatsapp.template.consultant": ("", False),
    "whatsapp.template.client": ("", False),
    "whatsapp.twilio.account_sid": ("", True),
    "whatsapp.twilio.auth_token": ("", True),
    "whatsapp.twilio.from": ("", False),
    "whatsapp.gupshup.api_key": ("", True),
    "whatsapp.gupshup.sender": ("", False),
    "whatsapp.provider_order": ("meta,twilio,gupshup", False),  # fallback chain
}

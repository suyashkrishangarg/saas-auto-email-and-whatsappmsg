from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ca_saas"
    REDIS_URL: str = "redis://localhost:6379/0"
    JWT_SECRET: str = "dev-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    FERNET_KEY: str = "dev-fernet-key-32-bytes-aaaaaaaaaa="
    # Pipeline runner: inline (free default, runs inside web service)
    # or celery (paid dedicated worker).
    WORKER_MODE: str = "inline"

    # Public URLs (same apex domain, different subdomains)
    FRONTEND_URL: str = "https://saas.ramyaai.tech"
    BACKEND_URL: str = "https://api.ramyaai.tech"
    INBOUND_DOMAIN: str = "inbound.ramyaai.tech"
    CORS_ORIGINS: List[str] = ["https://saas.ramyaai.tech", "http://localhost:3000"]

    # Google OAuth (mailbox watch)
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "https://api.ramyaai.tech/v1/gmail/oauth/callback"
    GOOGLE_PUBSUB_TOPIC: str = ""
    GOOGLE_PUBSUB_VERIFICATION_TOKEN: str = ""

    # Google login (dashboard SSO)
    GOOGLE_LOGIN_CLIENT_ID: str = ""
    GOOGLE_LOGIN_CLIENT_SECRET: str = ""
    GOOGLE_LOGIN_REDIRECT_URI: str = "https://saas.ramyaai.tech/auth/google/callback"

    # Fallback secrets (DB SystemSetting wins first)
    LLM_PROVIDER: str = ""
    LLM_MODEL: str = ""
    LLM_API_KEY: str = ""
    LLM_SYSTEM_PROMPT: str = ""
    WHATSAPP_PROVIDER: str = "meta"
    WHATSAPP_META_TOKEN: str = ""
    WHATSAPP_META_PHONE_NUMBER_ID: str = ""
    WHATSAPP_TEMPLATE_CONSULTANT: str = ""
    WHATSAPP_TEMPLATE_CLIENT: str = ""
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM: str = ""
    GUPSHUP_API_KEY: str = ""
    GUPSHUP_SENDER: str = ""

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            v = v.strip().strip("[]")
            return [o.strip().strip('"').strip("'") for o in v.split(",") if o.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

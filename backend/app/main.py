from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.core.database import AsyncSessionLocal, init_db
    from app.services.settings_service import SettingsService

    await init_db()  # create tables (dev convenience; Alembic in prod)
    try:
        async with AsyncSessionLocal() as db:
            await SettingsService(db).seed_defaults()
            await db.commit()
    except Exception:  # noqa: BLE001
        logging.getLogger("app").exception("settings seed failed")
    yield


app = FastAPI(
    title="CA Notice Intelligence Platform",
    version="1.0.0",
    description="B2B SaaS for Indian Tax Consultants: GST notice detection + WhatsApp alerts",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(api_router, prefix="/v1")


@app.get("/health")
async def health():
    return {"ok": True, "service": "ca-notice-platform"}

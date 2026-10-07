from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.database import get_db

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

def _cors_origins() -> list[str]:
    origins = list(settings.CORS_ORIGINS)
    # Vercel preview + production deployments (*.vercel.app) must always be
    # allowed, otherwise every frontend redeploy risks "Failed to fetch".
    # Render env CORS_ORIGINS overrides code defaults, so enforce it in code.
    for extra in (
        "https://saas-auto-email-and-whatsappmsg.vercel.app",
        "https://saas.ramyaai.tech",
    ):
        if extra not in origins:
            origins.append(extra)
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.options("/{path:path}")
async def cors_preflight(path: str, request: Request):
    origin = request.headers.get("origin", "*")
    return JSONResponse(
        {},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": request.headers.get(
                "access-control-request-headers", "authorization, content-type"
            ),
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Max-Age": "86400",
        },
    )

app.include_router(api_router, prefix="/v1")


@app.get("/health")
async def health():
    return {"ok": True, "service": "ca-notice-platform"}


@app.get("/health/db")
async def health_db(db=Depends(get_db)):
    """Touches the database (SELECT 1).

    Point your uptime monitor (UptimeRobot etc.) here every ~5 minutes to:
      1. keep your Render free web service awake, and
      2. keep the Neon/Supabase serverless Postgres compute from auto-suspending
         (kills cold-start latency on the first real request).
    """
    from sqlalchemy import text

    await db.execute(text("SELECT 1"))
    return {"ok": True, "db": "up"}

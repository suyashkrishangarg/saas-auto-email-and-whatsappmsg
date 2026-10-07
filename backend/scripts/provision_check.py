"""Live provisioning check: Neon Postgres + Upstash Redis + Celery broker.

Run from backend/:  python -m scripts.provision_check

1. connects to Postgres (SELECT 1) and reports connection mode
2. creates any missing tables (same as app startup / alembic)
3. seeds dynamic SystemSetting rows
4. PINGs Upstash Redis over TLS
5. verifies the Celery broker connection (kombu)
"""
from __future__ import annotations

import asyncio
import sys


async def main() -> int:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import settings
    from app.models import Base  # registers all models
    from app.services.settings_service import SettingsService

    ok = True
    db_url = settings.DATABASE_URL
    redis_url = settings.REDIS_URL
    print(f"DATABASE_URL : {db_url.split('@')[-1]}  (prefix={db_url.split('://')[0]})")
    print(f"REDIS_URL    : {redis_url.split('@')[-1]}  (scheme={redis_url.split('://')[0]})")

    # ---------- 1+2+3: Postgres ----------
    try:
        from app.core.database import prepare_engine_args

        clean_url, connect_args = prepare_engine_args(db_url)
        engine = create_async_engine(
            clean_url, connect_args=connect_args, pool_pre_ping=True
        )
        async with engine.connect() as conn:
            val = (await conn.execute(text("SELECT 1"))).scalar()
            print(f"[PG] connected, SELECT 1 -> {val}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema='public' ORDER BY table_name"
                    )
                )
            ).fetchall()
        print(f"[PG] tables: {[r[0] for r in rows]}")
        session = async_sessionmaker(engine, expire_on_commit=False)
        async with session() as s:
            await SettingsService(s).seed_defaults()
            await s.commit()
            n = (
                await s.execute(text("SELECT count(*) FROM system_settings"))
            ).scalar()
        print(f"[PG] system_settings seeded: {n} keys")
        await engine.dispose()
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"[PG] FAILED: {exc}")

    # ---------- 4: Upstash Redis (TLS) ----------
    try:
        import redis as redis_lib

        r = redis_lib.Redis.from_url(redis_url, socket_connect_timeout=10)
        print(f"[REDIS] PING -> {r.ping()}")
        r.close()
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"[REDIS] FAILED: {exc}")

    # ---------- 5: Celery broker via kombu ----------
    try:
        from app.workers.celery_app import celery_app

        with celery_app.connection() as conn:
            conn.ensure_connection(max_retries=2)
        print("[CELERY] broker connection OK")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"[CELERY] FAILED: {exc}")

    print("\nRESULT:", "ALL GOOD" if ok else "FIX ISSUES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

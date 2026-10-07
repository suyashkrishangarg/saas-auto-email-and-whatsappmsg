"""End-to-end API smoke test against SQLite (no external services needed).

Run: python -m tests.smoke
Covers: register -> login -> onboarding -> bulk grid save (with per-row
validation errors) -> client list -> admin metrics/settings -> notices feed.
"""
from __future__ import annotations

import asyncio
import os
import sys

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./smoke_test.db"
os.environ["FERNET_KEY"] = "smoke-test-key-32-bytes-long-xxxxxx"

import httpx  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core import database as dbmod  # noqa: E402
from app.core.config import settings  # noqa: E402

settings.DATABASE_URL = "sqlite+aiosqlite:///./smoke_test.db"

from app.main import app  # noqa: E402


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"{'PASS' if cond else 'FAIL'} - {label} {detail}")
    if not cond:
        raise AssertionError(f"{label}: {detail}")


async def run() -> None:
    engine = create_async_engine(settings.DATABASE_URL, future=True)
    dbmod.engine = engine
    dbmod.AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    if os.path.exists("smoke_test.db"):
        os.remove("smoke_test.db")

    from app.core.database import init_db
    from app.services.settings_service import SettingsService

    await init_db()
    async with dbmod.AsyncSessionLocal() as s:
        await SettingsService(s).seed_defaults()
        await s.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        # 1) register
        r = await c.post(
            "/v1/auth/register",
            json={"email": "ca@firm.in", "password": "Secret123", "full_name": "CA Ramya", "phone": "9876543210"},
        )
        check("register", r.status_code == 200, str(r.status_code) + r.text[:200])
        tok = r.json()["access_token"]
        hdr = {"Authorization": f"Bearer {tok}"}
        check("register role=CONSULTANT", r.json()["role"] == "CONSULTANT")

        # 2) bad phone rejected
        r = await c.post(
            "/v1/auth/register",
            json={"email": "bad@firm.in", "password": "Secret123", "phone": "12345"},
        )
        check("phone validation (12345 rejected)", r.status_code == 422, str(r.status_code))

        # 3) login
        r = await c.post("/v1/auth/login", json={"email": "ca@firm.in", "password": "Secret123"})
        check("login", r.status_code == 200, r.text[:150])

        # 4) onboarding: pick forwarding method
        r = await c.post("/v1/auth/onboarding", json={"auth_method": "FORWARDING"}, headers=hdr)
        check("onboarding", r.status_code == 200 and r.json()["forwarding_alias"], r.text[:200])

        # 5) bulk save (spreadsheet paste): 3 valid rows + 1 bad GSTIN + 1 bad phone
        r = await c.post(
            "/v1/clients/bulk",
            headers=hdr,
            json={
                "rows": [
                    {"consultant_phone": "9876543210", "client_name": "Alpha Traders", "client_phone": "+919811111111", "client_gstin": "29ABCDE1234F1Z5"},
                    {"client_name": "Beta Exports", "client_phone": "9822222222", "client_gstin": "27AAAAA1111A1Z1"},
                    {"client_name": "Gamma Ltd", "client_phone": "9833333333", "client_gstin": "07BBBBB2222B1Z2"},
                    {"client_name": "Bad GSTIN", "client_gstin": "TOOSHORT"},
                    {"client_name": "Bad Phone", "client_phone": "12", "client_gstin": "29CCCCC3333C1Z3"},
                ]
            },
        )
        check("bulk save partial success", r.status_code == 200, r.text[:300])
        body = r.json()
        check("created=3", body["created"] == 3, str(body))
        check("2 row errors reported", len(body["errors"]) == 2, str(body["errors"]))

        # 6) duplicate save -> updates
        r = await c.post(
            "/v1/clients/bulk",
            headers=hdr,
            json={"rows": [{"client_name": "Alpha Traders Pvt", "client_gstin": "29ABCDE1234F1Z5"}]},
        )
        check("upsert on same GSTIN", r.json()["updated"] == 1, r.text)

        # 7) client list
        r = await c.get("/v1/clients", headers=hdr)
        check("list clients = 3", r.status_code == 200 and len(r.json()) == 3, r.text[:200])

        # 8) notices feed + attention inbox
        r = await c.get("/v1/notices", headers=hdr)
        check("notices feed", r.status_code == 200 and r.json() == [], r.text[:150])
        r = await c.get("/v1/notices/unmatched", headers=hdr)
        check("attention inbox", r.status_code == 200 and r.json() == [], r.text[:150])

        # 9) non-admin blocked from /admin
        r = await c.get("/v1/admin/metrics", headers=hdr)
        check("consultant blocked from admin", r.status_code == 403, str(r.status_code))

        # 10) seed super admin directly, then admin metrics + settings
        from app.core.security import hash_password
        from app.models.user import Role, User

        async with dbmod.AsyncSessionLocal() as s:
            admin = User(
                email="root@ramyaai.tech",
                hashed_password=hash_password("RootPass123"),
                role=Role.SUPER_ADMIN,
            )
            s.add(admin)
            await s.commit()

        r = await c.post("/v1/auth/login", json={"email": "root@ramyaai.tech", "password": "RootPass123"})
        check("super admin login", r.status_code == 200, r.text[:150])
        ahdr = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = await c.get("/v1/admin/metrics", headers=ahdr)
        check("admin metrics", r.status_code == 200 and r.json()["consultants"] == 1, r.text[:300])

        r = await c.get("/v1/admin/settings", headers=ahdr)
        check("settings loaded", r.status_code == 200 and "llm.provider" in r.json(), r.text[:200])

        r = await c.put(
            "/v1/admin/settings",
            headers=ahdr,
            json={"key": "llm.provider", "value": "openai", "is_secret": False},
        )
        check("set llm.provider", r.status_code == 200, r.text)

        r = await c.put(
            "/v1/admin/settings",
            headers=ahdr,
            json={"key": "llm.api_key.openai", "value": "sk-test-123", "is_secret": True},
        )
        check("set secret key", r.status_code == 200, r.text)

        r = await c.get("/v1/admin/settings", headers=ahdr)
        s = r.json()
        check("provider visible", s["llm.provider"]["value"] == "openai", str(s["llm.provider"]))
        check(
            "secret decrypts for admin",
            s["llm.api_key.openai"]["value"] == "sk-test-123",
            str(s["llm.api_key.openai"]),
        )

        # 11) secret stored encrypted at rest
        import sqlite3

        con = sqlite3.connect("smoke_test.db")
        stored = con.execute(
            "SELECT value FROM system_settings WHERE key='llm.api_key.openai'"
        ).fetchone()[0]
        con.close()
        check("secret encrypted at rest", stored != "sk-test-123" and len(stored) > 30, stored[:40])

        # 12) admin users list shows client counts
        r = await c.get("/v1/admin/users", headers=ahdr)
        users = r.json()
        ca = [u for u in users if u["email"] == "ca@firm.in"][0]
        check("admin sees client_count=3", ca["client_count"] == 3, str(ca))

        # 13) suspend the consultant -> next call 403
        r = await c.patch(
            f"/v1/admin/users/{ca['id']}", headers=ahdr, json={"is_active": False}
        )
        check("suspend toggle", r.status_code == 200 and r.json()["is_active"] is False, r.text[:150])
        r = await c.get("/v1/clients", headers=hdr)
        check("suspended consultant blocked", r.status_code == 403, str(r.status_code))

        # 14) auth failure paths
        r = await c.get("/v1/clients")
        check("no token -> 401", r.status_code == 401, str(r.status_code))
        r = await c.post("/v1/auth/login", json={"email": "ca@firm.in", "password": "wrongpass"})
        check("wrong password -> 401", r.status_code == 401, str(r.status_code))

        # 15) audit logs endpoint
        r = await c.get("/v1/admin/logs", headers=ahdr)
        check("admin logs", r.status_code == 200, r.text[:150])

    await engine.dispose()
    print("\nALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except AssertionError as exc:
        print(f"\nSMOKE FAILED: {exc}")
        sys.exit(1)
    finally:
        import contextlib

        with contextlib.suppress(PermissionError, FileNotFoundError):
            if os.path.exists("smoke_test.db"):
                os.remove("smoke_test.db")

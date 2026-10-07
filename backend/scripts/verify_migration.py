"""Verify migration output: python scripts/verify_migration.py"""
import sqlite3
import sys

db = sys.argv[1] if len(sys.argv) > 1 else "mig_test.db"
con = sqlite3.connect(db)
tables = sorted(r[0] for r in con.execute("select name from sqlite_master where type='table'"))
expected = [
    "alembic_version",
    "clients",
    "google_credentials",
    "notices",
    "system_settings",
    "users",
    "whatsapp_logs",
]
missing = [t for t in expected if t not in tables]
idx = sorted(
    r[0]
    for r in con.execute(
        "select name from sqlite_master where type='index' and name like 'ix_%'"
    )
)
print("tables:", tables)
print("indexes:", idx)
print("missing:", missing or "none")
sys.exit(1 if missing else 0)

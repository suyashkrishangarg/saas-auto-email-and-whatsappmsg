# NoticeAlert — B2B GST Notice Intelligence for Indian CAs

End-to-end SaaS: detects incoming GST/Tax department notices (dual email channels),
matches them to clients via **AI-extracted GSTIN** (no regex anywhere), and dispatches
WhatsApp alerts to both consultant and client.

```
saas.ramyaai.tech   → Next.js frontend (this repo /frontend)   — separate Vercel project
api.ramyaai.tech    → FastAPI backend  (this repo /backend)    — Render/Railway/Fly
inbound.ramyaai.tech→ SendGrid/Postmark inbound + MX
```
Your existing site on `ramyaai.tech` stays untouched — subdomain = zero coupling, no extra cost.

---

## What's inside

| Layer | Tech |
|---|---|
| Backend | Python 3.11+, FastAPI (async), SQLAlchemy 2.0 async, Alembic, Pydantic v2 |
| Workers | Celery + Redis (queue `notices`) |
| DB | PostgreSQL (SQLite used for automated smoke tests) |
| Security | JWT + RBAC (SUPER_ADMIN / CONSULTANT), Fernet encryption for DB secrets |
| AI | Single LLM call → `is_official_notice, gstin, notice_form, financial_year, tax_period, demand_amount, due_date, summary`. Providers: OpenAI / Gemini / Anthropic / Groq — **super-admin selected, no hard default** |
| PDF | PyMuPDF → pdfplumber text extraction; **scanned PDF → AI vision fallback** (no OCR engine needed) |
| WhatsApp | Meta Cloud API → Twilio → Gupshup **fallback chain**, one retry per provider |
| Frontend | Next.js 14 App Router, TypeScript, Tailwind, TanStack Table (Excel-like paste grid) |

### Key flows
1. **Dual ingestion** — Gmail OAuth `users.watch` → Pub/Sub push → `/v1/ingest/pubsub`;
   or unique forwarding alias `notices-{id}@inbound.ramyaai.tech` → `/v1/ingest/inbound`.
   The inbound webhook **auto-intercepts Google's 9-digit forwarding code** and shows it
   in the dashboard banner (copy + confirm buttons).
2. **Pipeline** — extract → one AI call (GSTIN + notice fields) → exact DB match on
   `(consultant_id, gstin)` → WhatsApp to both, or **consultant-only alert + attention
   inbox** for unmapped GSTINs (map-to-client button re-dispatches client alert).
3. **Excel-like grid** — 4 columns (Consultant Phone, Client Name, Client WhatsApp, Client
   GSTIN), multi-row `Ctrl+V` paste from Excel/Sheets, draft state, **Save All** bulk upsert,
   per-row errors (simple checks only: 15-char alnum GSTIN, 10-digit phone + optional +91 —
   **zero regex per product spec**).
4. **`/admin` (role=SUPER_ADMIN)** — metrics (consultants, clients, notice volume, WhatsApp
   sent/failed, avg latency), user suspend/activate, audit logs, and the **dynamic settings
   engine** (provider/model/API keys/system prompt/WhatsApp creds, secrets Fernet-encrypted
   at rest, zero redeployment).

---

## Local development

### Backend
```bash
cd backend
python -m venv .venv && .venv\Scripts\activate     # or source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                             # set DATABASE_URL, JWT_SECRET, FERNET_KEY
uvicorn app.main:app --reload                      # http://localhost:8000/docs
celery -A app.workers.celery_app.celery_app worker --loglevel=info -Q notices
python -m scripts.seed_superuser admin@ramyaai.tech StrongPass123
```

### Frontend
```bash
cd frontend
npm install
# .env.local → NEXT_PUBLIC_API_URL=http://localhost:8000/v1
npm run dev                                        # http://localhost:3000
```

### Full stack via Docker
```bash
docker compose up --build
docker compose run --rm migrate                    # alembic upgrade head
```

### Tests (all passing)
```bash
cd backend && python -m tests.smoke    # 26 end-to-end API assertions incl. RBAC,
                                       # bulk grid save, Fernet encryption-at-rest
cd frontend && npx tsc --noEmit        # type-clean
cd frontend && npx next build         # production build, 11 routes
```

---

## Production datastores — **free forever** (avoid Render's 30-day DBs)

Render's free Postgres/Redis are **deleted after 30 days** (they're prototypes only).
Use these instead — swap two env vars, zero code changes:

| Piece | Service | Why |
|---|---|---|
| Postgres | **[Neon](https://neon.tech)** free | Serverless Postgres, persists forever, works with `asyncpg` |
| Redis | **[Upstash](https://upstash.com)** free | Redis over TLS (`rediss://`), Celery-compatible, persists forever |
| Frontend | **Vercel** free | Next.js native |
| API | **Render** free web service | sleeps after 15 min → keep awake with `/health/db` ping |
| Worker | **Railway (~$5/mo)** or **Render Starter ($7/mo)** or your own PC | a Celery worker must run 24/7 — no free tier runs it |

**Setup:** create Neon DB → copy **pooled** connection string → set as `DATABASE_URL`
(must contain `?sslmode=require`). Create Upstash DB → copy **TLS** URL → `REDIS_URL`.
Move both into Render env vars. Render's own DB/Redis services: don't create them at all.

> API URL form: `postgresql+asyncpg://user:pass@ep-xxx.aws.neon.tech/db?sslmode=require`
> Redis URL form: `rediss://default:<password>@xxx.upstash.io:6379`

**Keep everything warm:** add a free [UptimeRobot](https://uptimerobot.com) monitor hitting
`https://api.ramyaai.tech/health/db` every 5 minutes — keeps the Render web instance and
Neon compute awake (no cold starts). The new `/health/db` endpoint runs `SELECT 1` so the
DB connection pool stays live.

**Local development alternative:** `docker compose up --build` runs Postgres + Redis + API +
worker entirely on your machine — Render databases are never needed locally.

## DNS for `saas.ramyaai.tech` (free, existing site untouched)

| Record | Type | Name | Value |
|---|---|---|---|
| Frontend | CNAME | `saas` | `cname.vercel-dns.com` |
| API | CNAME | `api` | `cname.vercel-dns.com` / your host's target |
| Inbound mail | MX | `inbound` | provider's MX (SendGrid: `mx.sendgrid.net`) |

1. Vercel → Import this repo → project #2 → add domain `saas.ramyaai.tech` → auto SSL.
2. Same apex DNS zone as your current site, new records only — **your live site never changes**.
3. Backend env: `FRONTEND_URL=https://saas.ramyaai.tech`, `BACKEND_URL=https://api.ramyaai.tech`,
   `CORS_ORIGINS=["https://saas.ramyaai.tech"]` (see `backend/.env.example`).
4. SendGrid Inbound Parse route → `https://api.ramyaai.tech/v1/ingest/inbound`.
5. GCP Pub/Sub push subscription → `https://api.ramyaai.tech/v1/ingest/pubsub`.

Full deploy notes: `backend/DEPLOY.md`.

---

## Repo structure
```
backend/
  app/core       config, database, JWT+RBAC security, Fernet encryption
  app/models     User, GoogleCredential, Client, Notice, WhatsAppLog, SystemSetting (SQLAlchemy 2.0)
  app/schemas    Pydantic v2 request/response models + validators
  app/services   settings_service (DB→env), llm_service (4 providers + vision),
                 whatsapp_service (3-provider chain), pdf_extract, gmail_service, gstin
  app/api/v1     auth, clients, notices, ingestion (webhooks), gmail, admin
  app/workers    celery_app + tasks.py (full notice pipeline)
  alembic        0001_initial (7 tables, indexes, constraints)
  tests/smoke.py 26-assertion live API test
frontend/
  app/           login, register, auth/google/callback, dashboard, admin/{settings,logs}
  components/    ClientGrid (TanStack paste grid), ActivityFeed, AttentionInbox, SetupPanel
  lib/           api.ts (client + validators), auth.tsx (context)
```

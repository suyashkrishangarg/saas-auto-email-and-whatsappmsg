# ---- Backend (FastAPI + Celery worker) ----
# Deploy on Render / Railway / Fly.io. Subdomain: api.ramyaai.tech
#
# Procfile (Render web):
#   web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
#   worker: celery -A app.workers.celery_app.celery_app worker --loglevel=info -Q notices
#
# First deploy:
#   1. alembic upgrade head            (or rely on startup create_all in dev)
#   2. python -m scripts.seed_superuser admin@ramyaai.tech <password>
#   3. Configure DNS: api.ramyaai.tech -> CNAME your-service.onrender.com
#   4. Inbound route: SendGrid Inbound Parse -> POST https://api.ramyaai.tech/v1/ingest/inbound
#   5. Pub/Sub push:  subscription push endpoint -> https://api.ramyaai.tech/v1/ingest/pubsub

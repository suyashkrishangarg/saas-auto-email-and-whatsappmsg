"""Celery application bound to Redis."""
from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "ca_saas",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    task_default_queue="notices",
    task_routes={
        "app.workers.tasks.process_notice_email": {"queue": "notices"},
        "app.workers.tasks.process_gmail_message": {"queue": "notices"},
        "app.workers.tasks.dispatch_mapped_client_alert": {"queue": "notices"},
    },
)

"""Job runner: free-tier inline mode (default) with optional Celery later.

Inline mode: the pipeline runs inside the existing Render web service via
FastAPI BackgroundTasks. Zero extra services, zero cost, laptop stays off.

    WORKER_MODE=inline   (default) -> BackgroundTasks in web process
    WORKER_MODE=celery   -> .delay() to a dedicated worker (paid tier)

Usage from an endpoint:
    from app.workers.runner import enqueue
    from app.workers import tasks as pipeline
    enqueue(background, pipeline.run_forwarding(payload_dict))
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import BackgroundTasks

from app.core.config import settings

logger = logging.getLogger("runner")


def enqueue(background: BackgroundTasks | None, task_name: str, payload: Any) -> dict:
    """Schedule pipeline work; returns instantly with queued=True.

    Inline mode (default): Starlette awaits the coroutine AFTER the HTTP
    response is sent, so webhooks stay fast while the web process itself
    does the slow work (PDF -> AI -> WhatsApp). No worker process needed.
    """
    mode = (getattr(settings, "WORKER_MODE", "inline") or "inline").lower()
    if mode == "celery":
        try:
            from app.workers import tasks as pipeline

            getattr(pipeline, task_name).delay(payload)
            return {"ok": True, "queued": True, "mode": "celery"}
        except Exception:  # noqa: BLE001
            logger.exception("celery enqueue failed, falling back to inline")
    from app.workers import tasks as pipeline

    runner = pipeline.RUNNERS[task_name]
    if background is None:  # non-request context: run blocking
        import asyncio

        result = asyncio.run(runner(payload))
        return {"ok": True, "queued": False, "mode": "inline-sync", "result": result}
    background.add_task(runner, payload)
    return {"ok": True, "queued": True, "mode": "inline"}

"""Notice processing pipeline.

Flow: extract text (email body -> PDF text -> AI vision fallback)
      -> single LLM structured call (GSTIN + form + amount + due + summary)
      -> exact client lookup on consultant's GSTIN list (no pattern matching)
      -> persist Notice
      -> WhatsApp alerts (Meta->Twilio->Gupshup, one retry each)
         matched   : consultant + client
         unmatched : consultant only (map-to-client prompt)
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.encryption import decrypt
from app.models.client import Client
from app.models.google_credential import GoogleCredential
from app.models.notice import Notice, NoticeStatus
from app.models.user import User
from app.models.whatsapp_log import DeliveryStatus, RecipientType, WhatsAppLog
from app.services import gmail_service, llm_service, pdf_extract
from app.services.settings_service import SettingsService
from app.services.whatsapp_service import WhatsAppError, build_message, send_whatsapp
from app.workers.celery_app import celery_app

logger = logging.getLogger("pipeline")


# ------------------------------ Gmail fetch --------------------------------

async def _fetch_latest_message(access_token: str, history_id: str | None) -> Optional[dict]:
    """Return the newest INBOX message payload (headers + body + attachments)."""
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=45) as client:
        lst = await client.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers=headers,
            params={"labelIds": "INBOX", "maxResults": 1, "q": "is:unread"},
        )
        if lst.status_code >= 400:
            lst = await client.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                headers=headers,
                params={"labelIds": "INBOX", "maxResults": 1},
            )
        lst.raise_for_status()
        ids = [m["id"] for m in lst.json().get("messages", [])]
        if not ids:
            return None
        msg = await client.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{ids[0]}",
            headers=headers,
            params={"format": "full"},
        )
        msg.raise_for_status()
        return msg.json()


def _headers_to_dict(payload: dict) -> dict:
    out = {}
    for h in payload.get("headers", []):
        out[h.get("name", "").lower()] = h.get("value", "")
    return out


# ------------------------------ entrypoints --------------------------------

@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def process_notice_email(self, payload: dict):
    """Inbound-forwarding channel entrypoint (already has text body)."""
    try:
        return asyncio.run(_handle_forwarding(payload))
    except Exception as exc:  # noqa: BLE001
        logger.exception("process_notice_email failed")
        self.update_state(state="FAILED", meta={"error": str(exc)})
        asyncio.run(_persist_failure(payload, str(exc)))
        return {"ok": False, "error": str(exc)}


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def process_gmail_message(self, payload: dict):
    """Gmail watch channel entrypoint: fetch newest message, then run pipeline."""
    try:
        return asyncio.run(_handle_gmail(payload))
    except Exception as exc:  # noqa: BLE001
        logger.exception("process_gmail_message failed")
        self.update_state(state="FAILED", meta={"error": str(exc)})
        asyncio.run(_persist_failure(payload, str(exc)))
        return {"ok": False, "error": str(exc)}


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def dispatch_mapped_client_alert(self, notice_id: str):
    """Send the client WhatsApp after the consultant maps an unmatched notice."""
    try:
        return asyncio.run(_send_client_after_map(UUID(notice_id)))
    except Exception as exc:  # noqa: BLE001
        logger.exception("dispatch_mapped_client_alert failed")
        return {"ok": False, "error": str(exc)}


# ------------------------------ handlers -----------------------------------

async def _handle_forwarding(payload: dict) -> dict:
    consultant_id = UUID(payload["consultant_id"])
    subject = payload.get("subject") or ""
    sender = payload.get("sender") or ""
    text = payload.get("text") or ""
    html = payload.get("html") or ""
    if not text.strip() and html.strip():
        text = pdf_extract.extract_email_body_html_to_text(html)

    attachment_text_parts: list[str] = []
    attachment_pdfs: list[bytes] = []
    for item in payload.get("attachments") or []:
        raw = await _download_attachment(item)
        if raw is None:
            continue
        extracted = pdf_extract.extract_pdf_text(raw)
        if extracted:
            attachment_text_parts.append(extracted)
            attachment_pdfs.append(raw)

    return await _run_pipeline(
        consultant_id=consultant_id,
        subject=subject,
        sender=sender,
        body_text=text,
        attachment_text="\n".join(attachment_text_parts),
        attachment_pdfs=attachment_pdfs,
        source="FORWARDING",
    )


async def _handle_gmail(payload: dict) -> dict:
    consultant_id = UUID(payload["consultant_id"])
    async with AsyncSessionLocal() as db:
        cred = (
            await db.execute(select(GoogleCredential).where(GoogleCredential.user_id == consultant_id))
        ).scalar_one_or_none()
        if cred is None:
            return {"ok": False, "error": "Gmail not connected"}
        token = await gmail_service.ensure_fresh_token(cred)
        cred.last_sync_at = datetime.now(timezone.utc)
        await db.commit()
        message = await _fetch_latest_message(token or "", payload.get("history_id"))
        if not message:
            return {"ok": True, "skipped": "no messages"}

        inner = message.get("payload", {})
        hdrs = _headers_to_dict(inner)
        body_text, pdfs = pdf_extract.extract_from_email_parts(inner.get("parts", []) or [inner])
        if not body_text:
            body_data = (inner.get("body") or {}).get("data")
            if body_data:
                body_text = pdf_extract.decode_email_part(body_data)

        attachment_text_parts = []
        for raw in pdfs:
            t = pdf_extract.extract_pdf_text(raw)
            if t:
                attachment_text_parts.append(t)

        return await _run_pipeline(
            consultant_id=consultant_id,
            subject=hdrs.get("subject", ""),
            sender=hdrs.get("from", ""),
            body_text=body_text,
            attachment_text="\n".join(attachment_text_parts),
            attachment_pdfs=pdfs,
            source="GMAIL",
        )


async def _download_attachment(item) -> Optional[bytes]:
    url = item.get("url") if isinstance(item, dict) else None
    if not url:
        return None
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.content
    except Exception as exc:  # noqa: BLE001
        logger.warning("attachment download failed: %s", exc)
    return None


async def _persist_failure(payload: dict, error: str) -> None:
    try:
        consultant_id = payload.get("consultant_id")
        if not consultant_id:
            return
        async with AsyncSessionLocal() as db:
            db.add(
                Notice(
                    consultant_id=UUID(consultant_id),
                    raw_subject=(payload.get("subject") or "")[:500],
                    sender=payload.get("sender"),
                    status=NoticeStatus.FAILED,
                    error_message=error[:4000],
                    source=payload.get("source"),
                )
            )
            await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("_persist_failure failed")


# ------------------------------ core pipeline -------------------------------

async def _run_pipeline(
    *,
    consultant_id: UUID,
    subject: str,
    sender: str,
    body_text: str,
    attachment_text: str,
    attachment_pdfs: list[bytes],
    source: str,
) -> dict:
    started = time.perf_counter()
    async with AsyncSessionLocal() as db:
        svc = SettingsService(db)
        llm_cfg = await svc.get_llm_config()
        wa_cfg = await svc.get_whatsapp_config()
        system_prompt = await svc.get("llm.system_prompt", "")

        consultant = await db.get(User, consultant_id)
        if consultant is None:
            return {"ok": False, "error": "consultant not found"}

        # 1) AI analysis - single structured call (GSTIN included)
        try:
            analysis = await llm_service.analyse_notice(
                subject=subject,
                body_text=body_text,
                attachment_text=attachment_text,
                cfg=llm_cfg,
                system_prompt_override=system_prompt,
            )
        except llm_service.LLMError as first_err:
            can_vision = bool(attachment_pdfs) and (
                not attachment_text.strip() or "vision" in str(first_err).lower()
            )
            if can_vision:
                try:
                    pages = pdf_extract.render_pages_base64(attachment_pdfs[0])
                    analysis = await llm_service.analyse_notice_vision(
                        subject=subject,
                        page_images_base64=pages,
                        cfg=llm_cfg,
                        system_prompt_override=system_prompt,
                    )
                except llm_service.LLMError as vision_err:
                    return await _fail(
                        db, consultant_id, subject, sender, source, str(vision_err), started
                    )
            else:
                return await _fail(db, consultant_id, subject, sender, source, str(first_err), started)

        if not analysis.get("is_official_notice"):
            return {"ok": True, "skipped": "not an official notice"}

        # 2) deterministic exact match against this consultant's client list
        gstin = analysis.get("gstin")
        client: Optional[Client] = None
        if gstin:
            client = (
                await db.execute(
                    select(Client).where(
                        Client.consultant_id == consultant_id, Client.gstin == gstin
                    )
                )
            ).scalar_one_or_none()

        # 3) persist notice
        notice = Notice(
            consultant_id=consultant_id,
            client_id=client.id if client else None,
            raw_subject=(subject or "")[:500],
            sender=(sender or "")[:320],
            extracted_gstin=gstin,
            is_official_notice=True,
            notice_form=analysis.get("notice_form"),
            financial_year=analysis.get("financial_year"),
            tax_period=analysis.get("tax_period"),
            demand_amount=analysis.get("demand_amount"),
            due_date=date.fromisoformat(analysis["due_date"]) if analysis.get("due_date") else None,
            summary=analysis.get("summary"),
            status=NoticeStatus.PROCESSED if client else NoticeStatus.UNMATCHED,
            source=source,
        )
        db.add(notice)
        await db.flush()

        # 4) WhatsApp dispatch
        sent = failed = 0
        due_str = analysis.get("due_date") or ""
        if client:
            for kind, phone, target in (
                ("CONSULTANT", consultant.phone, "consultant"),
                ("CLIENT", client.phone, "client"),
            ):
                msg = build_message(
                    recipient_kind=kind,
                    client_name=client.name,
                    gstin=gstin,
                    notice_form=analysis.get("notice_form"),
                    demand_amount=analysis.get("demand_amount"),
                    due_date=due_str,
                    summary=analysis.get("summary"),
                )
                sent, failed = await _dispatch_one(
                    db, wa_cfg, notice, RecipientType(kind), phone, msg, sent, failed
                )
        else:
            unmapped_msg = build_message(
                recipient_kind="CONSULTANT",
                client_name="",
                gstin=gstin,
                notice_form=analysis.get("notice_form"),
                demand_amount=analysis.get("demand_amount"),
                due_date=due_str,
                summary=analysis.get("summary"),
                is_unmapped=True,
            )
            sent, failed = await _dispatch_one(
                db, wa_cfg, notice, RecipientType.CONSULTANT,
                consultant.phone, unmapped_msg, sent, failed,
            )

        notice.processing_latency_ms = int((time.perf_counter() - started) * 1000)
        await db.commit()
        return {
            "ok": True,
            "notice_id": str(notice.id),
            "matched": bool(client),
            "gstin": gstin,
            "whatsapp_sent": sent,
            "whatsapp_failed": failed,
            "latency_ms": notice.processing_latency_ms,
        }


async def _dispatch_one(db, wa_cfg, notice, rtype, phone, message, sent, failed):
    if not phone:
        db.add(
            WhatsAppLog(
                notice_id=notice.id,
                recipient_type=rtype,
                recipient_phone="",
                status=DeliveryStatus.FAILED,
                error_message="No phone number on record",
            )
        )
        return sent, failed + 1
    try:
        provider, mid, _ = await send_whatsapp(wa_cfg, phone, message)
        db.add(
            WhatsAppLog(
                notice_id=notice.id,
                recipient_type=rtype,
                recipient_phone=phone,
                provider=provider,
                message_id=mid,
                status=DeliveryStatus.SENT,
            )
        )
        return sent + 1, failed
    except WhatsAppError as exc:
        db.add(
            WhatsAppLog(
                notice_id=notice.id,
                recipient_type=rtype,
                recipient_phone=phone,
                provider=exc.provider,
                status=DeliveryStatus.FAILED,
                error_message=str(exc)[:2000],
            )
        )
        return sent, failed + 1


async def _fail(db, consultant_id, subject, sender, source, error, started) -> dict:
    db.add(
        Notice(
            consultant_id=consultant_id,
            raw_subject=(subject or "")[:500],
            sender=(sender or "")[:320],
            status=NoticeStatus.FAILED,
            error_message=error[:4000],
            source=source,
            processing_latency_ms=int((time.perf_counter() - started) * 1000),
        )
    )
    await db.commit()
    return {"ok": False, "error": error}


async def _send_client_after_map(notice_id: UUID) -> dict:
    """Post-mapping: dispatch the CLIENT alert for a previously unmatched notice."""
    async with AsyncSessionLocal() as db:
        notice = await db.get(Notice, notice_id)
        if notice is None or notice.client_id is None:
            return {"ok": False, "error": "notice or client missing"}
        client = await db.get(Client, notice.client_id)
        consultant = await db.get(User, notice.consultant_id)
        if client is None or consultant is None:
            return {"ok": False, "error": "client/consultant missing"}

        svc = SettingsService(db)
        wa_cfg = await svc.get_whatsapp_config()
        msg = build_message(
            recipient_kind="CLIENT",
            client_name=client.name,
            gstin=notice.extracted_gstin,
            notice_form=notice.notice_form,
            demand_amount=notice.demand_amount,
            due_date=notice.due_date.isoformat() if notice.due_date else "",
            summary=notice.summary,
        )
        sent, failed = await _dispatch_one(
            db, wa_cfg, notice, RecipientType.CLIENT, client.phone, msg, 0, 0
        )
        await db.commit()
        return {"ok": True, "sent": sent, "failed": failed}

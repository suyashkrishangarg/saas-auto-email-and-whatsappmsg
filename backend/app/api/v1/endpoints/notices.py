from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_consultant
from app.models.client import Client
from app.models.notice import Notice, NoticeStatus
from app.models.user import User
from app.models.whatsapp_log import DeliveryStatus, RecipientType, WhatsAppLog
from app.schemas import MapNoticeIn, NoticeOut

router = APIRouter()


@router.get("", response_model=list[NoticeOut])
async def list_notices(
    status: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_consultant),
):
    q = select(Notice).where(Notice.consultant_id == user.id)
    if status:
        try:
            q = q.where(Notice.status == NoticeStatus(status))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid status") from exc
    q = q.order_by(Notice.created_at.desc()).limit(min(limit, 500))
    return (await db.execute(q)).scalars().all()


@router.get("/unmatched", response_model=list[NoticeOut])
async def attention_inbox(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_consultant),
):
    """Notices awaiting client mapping."""
    q = (
        select(Notice)
        .where(Notice.consultant_id == user.id, Notice.status == NoticeStatus.UNMATCHED)
        .order_by(Notice.created_at.desc())
        .limit(200)
    )
    return (await db.execute(q)).scalars().all()


@router.post("/{notice_id}/map", response_model=NoticeOut)
async def map_to_client(
    notice_id: UUID,
    payload: MapNoticeIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_consultant),
):
    """Map an unmatched notice to an existing client, then dispatch client WhatsApp."""
    notice = await db.get(Notice, notice_id)
    if notice is None or notice.consultant_id != user.id:
        raise HTTPException(status_code=404, detail="Notice not found")
    client = await db.get(Client, payload.client_id)
    if client is None or client.consultant_id != user.id:
        raise HTTPException(status_code=404, detail="Client not found")

    notice.client_id = client.id
    notice.status = NoticeStatus.PROCESSED
    await db.commit()

    # Enqueue client alert (same pipeline task, lighter mode)
    from app.workers.tasks import dispatch_mapped_client_alert

    dispatch_mapped_client_alert.delay(str(notice.id))
    await db.refresh(notice)
    return notice


@router.get("/{notice_id}/logs")
async def notice_logs(
    notice_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_consultant),
):
    notice = await db.get(Notice, notice_id)
    if notice is None or notice.consultant_id != user.id:
        raise HTTPException(status_code=404, detail="Notice not found")
    rows = (
        (
            await db.execute(
                select(WhatsAppLog).where(WhatsAppLog.notice_id == notice_id).order_by(WhatsAppLog.sent_at)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(r.id),
            "recipient_type": r.recipient_type.value,
            "recipient_phone": r.recipient_phone,
            "provider": r.provider,
            "message_id": r.message_id,
            "status": r.status.value,
            "error_message": r.error_message,
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
        }
        for r in rows
    ]


@router.get("/stats/summary")
async def stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_consultant),
):
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    total = await db.scalar(
        select(func.count()).select_from(Notice).where(Notice.consultant_id == user.id)
    )
    unmatched = await db.scalar(
        select(func.count())
        .select_from(Notice)
        .where(Notice.consultant_id == user.id, Notice.status == NoticeStatus.UNMATCHED)
    )
    day = await db.scalar(
        select(func.count())
        .select_from(Notice)
        .where(Notice.consultant_id == user.id, Notice.created_at >= since)
    )
    clients = await db.scalar(
        select(func.count()).select_from(Client).where(Client.consultant_id == user.id)
    )
    return {
        "notices_total": total or 0,
        "unmatched": unmatched or 0,
        "notices_24h": day or 0,
        "clients": clients or 0,
    }

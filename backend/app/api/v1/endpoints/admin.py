"""Super admin portal APIs - role = SUPER_ADMIN protected."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_super_admin
from app.models.client import Client
from app.models.notice import Notice, NoticeStatus
from app.models.system_setting import SystemSetting
from app.models.user import Role, User
from app.models.whatsapp_log import DeliveryStatus, WhatsAppLog
from app.schemas import AdminMetrics, SettingIn, UserAdminUpdate, UserOut
from app.services.settings_service import SettingsService

router = APIRouter()


@router.get("/metrics", response_model=AdminMetrics)
async def metrics(db: AsyncSession = Depends(get_db), _: User = Depends(require_super_admin)):
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)

    consultants = await db.scalar(
        select(func.count()).select_from(User).where(User.role == Role.CONSULTANT)
    )
    active = await db.scalar(
        select(func.count())
        .select_from(User)
        .where(User.role == Role.CONSULTANT, User.is_active.is_(True))
    )
    clients = await db.scalar(select(func.count()).select_from(Client))
    notices_total = await db.scalar(select(func.count()).select_from(Notice))
    notices_24h = await db.scalar(
        select(func.count()).select_from(Notice).where(Notice.created_at >= day_ago)
    )
    unmatched = await db.scalar(
        select(func.count()).select_from(Notice).where(Notice.status == NoticeStatus.UNMATCHED)
    )
    wa_sent = await db.scalar(
        select(func.count()).select_from(WhatsAppLog).where(WhatsAppLog.status == DeliveryStatus.SENT)
    )
    wa_failed = await db.scalar(
        select(func.count()).select_from(WhatsAppLog).where(WhatsAppLog.status == DeliveryStatus.FAILED)
    )
    avg_lat = await db.scalar(
        select(func.avg(Notice.processing_latency_ms)).where(
            Notice.processing_latency_ms.isnot(None)
        )
    )
    return AdminMetrics(
        consultants=consultants or 0,
        active_consultants=active or 0,
        suspended=(consultants or 0) - (active or 0),
        clients=clients or 0,
        notices_total=notices_total or 0,
        notices_24h=notices_24h or 0,
        unmatched=unmatched or 0,
        whatsapp_sent=wa_sent or 0,
        whatsapp_failed=wa_failed or 0,
        avg_latency_ms=float(avg_lat) if avg_lat else None,
    )


@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db), _: User = Depends(require_super_admin)):
    users = (await db.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    out = []
    for u in users:
        client_count = await db.scalar(
            select(func.count()).select_from(Client).where(Client.consultant_id == u.id)
        )
        notice_count = await db.scalar(
            select(func.count()).select_from(Notice).where(Notice.consultant_id == u.id)
        )
        wa_sent = await db.scalar(
            select(func.count())
            .select_from(WhatsAppLog)
            .join(Notice, WhatsAppLog.notice_id == Notice.id)
            .where(Notice.consultant_id == u.id, WhatsAppLog.status == DeliveryStatus.SENT)
        )
        wa_failed = await db.scalar(
            select(func.count())
            .select_from(WhatsAppLog)
            .join(Notice, WhatsAppLog.notice_id == Notice.id)
            .where(Notice.consultant_id == u.id, WhatsAppLog.status == DeliveryStatus.FAILED)
        )
        lat = await db.scalar(
            select(func.avg(Notice.processing_latency_ms)).where(
                Notice.consultant_id == u.id, Notice.processing_latency_ms.isnot(None)
            )
        )
        conn = (
            await db.execute(select(SystemSetting).where(SystemSetting.key == f"conn.{u.id}"))
        ).scalar_one_or_none()
        out.append(
            {
                "id": str(u.id),
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role.value,
                "phone": u.phone,
                "auth_method": u.auth_method.value,
                "forwarding_alias": u.forwarding_alias,
                "is_active": u.is_active,
                "client_count": client_count or 0,
                "notice_count": notice_count or 0,
                "whatsapp_sent": wa_sent or 0,
                "whatsapp_failed": wa_failed or 0,
                "avg_latency_ms": float(lat) if lat else None,
                "connection_status": (conn.value if conn else None)
                or ("WATCHING" if u.auth_method.value in ("OAUTH", "BOTH") else "FORWARDING"),
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
        )
    return out


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: UUID,
    payload: UserAdminUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.role:
        try:
            user.role = Role(payload.role)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid role") from exc
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/settings")
async def get_settings(db: AsyncSession = Depends(get_db), _: User = Depends(require_super_admin)):
    svc = SettingsService(db)
    return await svc.all()


@router.put("/settings")
async def put_setting(
    payload: SettingIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    svc = SettingsService(db)
    await svc.set(payload.key, payload.value, payload.is_secret)
    await db.commit()
    return {"ok": True, "key": payload.key}


@router.post("/settings/seed")
async def seed(db: AsyncSession = Depends(get_db), _: User = Depends(require_super_admin)):
    svc = SettingsService(db)
    await svc.seed_defaults()
    await db.commit()
    return {"ok": True}


@router.get("/logs")
async def audit_logs(
    kind: str = "all",
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """Unified observability: processed emails (notices) + WhatsApp receipts."""
    items: list[dict] = []

    if kind in ("all", "notices"):
        rows = (
            (await db.execute(select(Notice).order_by(Notice.created_at.desc()).limit(limit)))
            .scalars()
            .all()
        )
        for n in rows:
            items.append(
                {
                    "type": "EMAIL",
                    "id": str(n.id),
                    "at": n.created_at.isoformat() if n.created_at else None,
                    "consultant_id": str(n.consultant_id),
                    "subject": n.raw_subject,
                    "sender": n.sender,
                    "source": n.source,
                    "gstin": n.extracted_gstin,
                    "status": n.status.value,
                    "latency_ms": n.processing_latency_ms,
                    "error": n.error_message,
                }
            )

    if kind in ("all", "whatsapp"):
        rows = (
            (
                await db.execute(
                    select(WhatsAppLog).order_by(WhatsAppLog.sent_at.desc()).limit(limit)
                )
            )
            .scalars()
            .all()
        )
        for w in rows:
            items.append(
                {
                    "type": "WHATSAPP",
                    "id": str(w.id),
                    "at": w.sent_at.isoformat() if w.sent_at else None,
                    "notice_id": str(w.notice_id),
                    "recipient_type": w.recipient_type.value,
                    "phone": w.recipient_phone,
                    "provider": w.provider,
                    "message_id": w.message_id,
                    "status": w.status.value,
                    "error": w.error_message,
                }
            )

    items.sort(key=lambda x: x.get("at") or "", reverse=True)
    return items[:limit]

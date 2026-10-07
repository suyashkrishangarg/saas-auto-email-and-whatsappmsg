from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_consultant
from app.models.client import Client
from app.models.user import User
from app.schemas import BulkResult, ClientBulkIn, ClientOut, ClientRowIn

router = APIRouter()


@router.get("", response_model=list[ClientOut])
async def list_clients(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_consultant),
):
    result = await db.execute(select(Client).where(Client.consultant_id == user.id).order_by(Client.name))
    return result.scalars().all()


@router.post("/bulk", response_model=BulkResult)
async def bulk_save(
    payload: ClientBulkIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_consultant),
):
    """Spreadsheet paste flow: one request saves the whole draft grid.

    Errors are returned per-row (index + message) so the UI can highlight cells
    without failing the entire batch.
    """
    existing = {
        c.gstin: c
        for c in (
            (await db.execute(select(Client).where(Client.consultant_id == user.id)))
            .scalars()
            .all()
        )
    }
    created = updated = 0
    errors: list[dict] = []

    for idx, raw in enumerate(payload.rows):
        try:
            row = ClientRowIn(**raw)
        except ValidationError as exc:
            msg = "; ".join(
                f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()
            )
            errors.append(
                {"row": idx + 1, "gstin": raw.get("client_gstin", ""), "error": msg}
            )
            continue
        try:
            if row.client_gstin in existing:
                client = existing[row.client_gstin]
                client.name = row.client_name.strip()
                if row.client_phone:
                    client.phone = row.client_phone
                updated += 1
            else:
                obj = Client(
                    consultant_id=user.id,
                    name=row.client_name.strip(),
                    phone=row.client_phone,
                    gstin=row.client_gstin,
                )
                db.add(obj)
                existing[row.client_gstin] = obj
                created += 1
        except Exception as exc:  # per-row model validation failure
            errors.append({"row": idx + 1, "gstin": row.client_gstin, "error": str(exc)})

    await db.flush()
    return BulkResult(created=created, updated=updated, errors=errors)


@router.put("/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: UUID,
    row: ClientRowIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_consultant),
):
    client = await db.get(Client, client_id)
    if client is None or client.consultant_id != user.id:
        raise HTTPException(status_code=404, detail="Client not found")
    try:
        client.name = row.client_name.strip()
        client.phone = row.client_phone
        client.gstin = row.client_gstin
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(client)
    return client


@router.delete("/{client_id}")
async def delete_client(
    client_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_consultant),
):
    client = await db.get(Client, client_id)
    if client is None or client.consultant_id != user.id:
        raise HTTPException(status_code=404, detail="Client not found")
    await db.delete(client)
    await db.commit()
    return {"ok": True}

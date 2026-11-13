from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.core.queue import get_queue_pool
from app.db.session import get_db
from app.integrations.mercadolivre.client import MercadoLivreClient, MercadoLivreError
from app.models import FullInventory, FullOperation, MarketplaceAccount, User
from app.api.routes.integrations_mercadolivre_full_common import _account, _serialize_inventory

router = APIRouter()

@router.get("/status")
def full_status(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.MARKETPLACE_READ)),
):
    account = db.scalar(
        select(MarketplaceAccount)
        .where(MarketplaceAccount.active.is_(True), MarketplaceAccount.provider == "mercadolivre")
        .order_by(MarketplaceAccount.created_at)
        .limit(1)
    )
    if account is None:
        return {"connected": False, "seller_id": None, "last_sync": None}
    last_sync = db.scalar(
        select(FullInventory.synced_at)
        .where(FullInventory.account_id == account.id)
        .order_by(FullInventory.synced_at.desc())
        .limit(1)
    )
    return {
        "connected": True,
        "seller_id": account.seller_id,
        "nickname": account.nickname,
        "last_sync": last_sync,
    }


@router.post("/sync")
async def sync_now(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.MARKETPLACE_PROCESS)),
):
    account = _account(db)
    pool = await get_queue_pool()
    job = await pool.enqueue_job(
        "sync_mercadolivre_full", account.id, _job_id=f"ml-full-{account.id}"
    )
    return {
        "accepted": job is not None,
        "message": (
            "Sincronização do Full solicitada."
            if job
            else "Já existe uma sincronização em andamento."
        ),
    }


@router.post("/operations/backfill")
async def backfill_operations(
    date_from: date,
    date_to: date,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.MARKETPLACE_PROCESS)),
):
    today = datetime.now(UTC).date()
    if date_from > date_to or (date_to - date_from).days > 59:
        raise HTTPException(422, "Informe uma janela de até 60 dias.")
    if date_to > today or date_from < today - timedelta(days=365):
        raise HTTPException(422, "O histórico disponível é limitado aos últimos 12 meses.")
    account = _account(db)
    pool = await get_queue_pool()
    job_id = f"ml-full-backfill-{account.id}-{date_from.isoformat()}-{date_to.isoformat()}"
    job = await pool.enqueue_job(
        "sync_mercadolivre_full",
        account.id,
        date_from.isoformat(),
        date_to.isoformat(),
        _job_id=job_id,
    )
    return {
        "accepted": job is not None,
        "message": (
            "Backfill de movimentações solicitado."
            if job
            else "Este backfill já está na fila ou em andamento."
        ),
    }


@router.get("/inventory")
def inventory(
    q: str | None = None,
    low: bool = False,
    zero: bool = False,
    unavailable: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.MARKETPLACE_READ)),
):
    account = _account(db)
    rows = db.scalars(
        select(FullInventory)
        .where(FullInventory.account_id == account.id)
        .order_by(FullInventory.inventory_id)
    ).all()
    result = []
    for row in rows:
        if zero and row.available_quantity != 0:
            continue
        if low and (
            row.available_quantity is None or row.available_quantity > 2
        ):
            continue
        if unavailable and not (row.not_available_quantity or 0) > 0:
            continue
        data = _serialize_inventory(row, db)
        search_blob = " ".join(
            [
                row.inventory_id,
                str(row.links),
                str(row.not_available_detail),
                str(row.external_references),
            ]
        )
        if q and q.casefold() not in search_blob.casefold():
            continue
        result.append(data)
    unavailable_total = sum(row.not_available_quantity or 0 for row in rows)
    available_total = sum(row.available_quantity or 0 for row in rows)
    stored_total = sum(row.total or 0 for row in rows)
    return {
        "items": result,
        "count": len(result),
        "summary": {
            "available": available_total,
            "unavailable": unavailable_total,
            "stored": stored_total,
            "partial": any(row.sync_status != "ok" for row in rows),
            "missing": sum(row.available_quantity is None for row in rows),
        },
    }


@router.get("/replenishment/{user_product_id}")
def replenishment_detail(
    user_product_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.MARKETPLACE_READ)),
):
    account = _account(db)
    linked_ids = {
        str(link.get("user_product_id"))
        for row in db.scalars(select(FullInventory).where(FullInventory.account_id == account.id))
        for link in row.links or []
        if link.get("user_product_id")
    }
    if user_product_id not in linked_ids:
        raise HTTPException(404, "Produto Full não encontrado nesta conta.")
    client = MercadoLivreClient(db, account)
    try:
        data = client.get(
            f"/marketplace/fbm/user-products/{user_product_id}/replenishment"
        )
    except MercadoLivreError as exc:
        if exc.status_code in {403, 404}:
            return {"available": False, "reason": "Recomendação indisponível para esta conta."}
        raise HTTPException(502, "Não foi possível consultar a recomendação.") from exc
    return {"available": True, "data": data}


@router.get("/operations")
def operations(
    date_from: date | None = None,
    date_to: date | None = None,
    inventory_id: str | None = None,
    sku: str | None = None,
    inbound_id: str | None = None,
    operation_type: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.MARKETPLACE_READ)),
):
    account = _account(db)
    end = date_to or datetime.now(UTC).date()
    start = date_from or end - timedelta(days=30)
    if start > end or (end - start).days > 59:
        raise HTTPException(422, "Cada consulta pode cobrir até 60 dias.")
    query = select(FullOperation).where(
        FullOperation.account_id == account.id,
        FullOperation.date_created >= datetime.combine(start, datetime.min.time(), UTC),
        FullOperation.date_created
        < datetime.combine(end + timedelta(days=1), datetime.min.time(), UTC),
    )
    if inventory_id:
        query = query.where(FullOperation.inventory_id == inventory_id)
    if inbound_id:
        query = query.where(FullOperation.inbound_id == inbound_id)
    if operation_type:
        query = query.where(FullOperation.operation_type == operation_type.upper())
    if sku:
        matched_inventories = [
            row.inventory_id
            for row in db.scalars(
                select(FullInventory).where(FullInventory.account_id == account.id)
            )
            if any(str(link.get("sku") or "").casefold() == sku.casefold() for link in row.links or [])
        ]
        query = query.where(FullOperation.inventory_id.in_(matched_inventories))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(FullOperation.date_created.desc()).offset(offset).limit(limit)).all()
    inventory_rows = db.scalars(
        select(FullInventory).where(FullInventory.account_id == account.id)
    ).all()
    return {
        "total": total,
        "next_offset": offset + len(rows) if offset + len(rows) < total else None,
        "items": [
            {
                "id": row.operation_id,
                "inventory_id": row.inventory_id,
                "inbound_id": row.inbound_id,
                "date_created": (row.date_created.replace(tzinfo=UTC) if row.date_created and row.date_created.tzinfo is None else row.date_created),
                "type": row.operation_type,
                "detail": row.detail,
                "result": row.result,
                "external_references": row.external_references,
            }
            for row in rows
        ],
        "coverage_start": min(
            (row.operations_coverage_start for row in inventory_rows if row.operations_coverage_start),
            default=None,
        ),
        "coverage_end": max(
            (row.operations_coverage_end for row in inventory_rows if row.operations_coverage_end),
            default=None,
        ),
        "partial": any(row.operations_sync_status != "ok" for row in inventory_rows),
    }

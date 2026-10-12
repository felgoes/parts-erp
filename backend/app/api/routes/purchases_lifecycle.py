from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.api.routes.purchases_payables import (
    _active_payable,
    _payable_with_payments,
    _sync_payable,
)
from app.api.routes.purchases_receiving import (
    _pending_return,
    _register_returns,
)
from app.api.routes.purchases_support import (
    _apply_supplier_defaults,
    _event,
    _load,
    _present,
)
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import (
    MarketStudy,
    MovementType,
    PurchaseCase,
    PurchaseDeletion,
    PurchaseItem,
    Supplier,
    User,
)
from app.schemas.common import (
    PurchaseCancelRequest,
    PurchaseCloseRequest,
    PurchaseDeletionOut,
    PurchaseOut,
    PurchaseUpdate,
)
from app.services.stock import move_stock

router = APIRouter(prefix="/purchases", tags=["Compras"])


def _delete_blockers(purchase: PurchaseCase) -> list[str]:
    blockers: list[str] = []
    if purchase.selected_quote_id:
        blockers.append("cotação escolhida")
    if purchase.ordered_at:
        blockers.append("pedido enviado ao fornecedor")
    if any(Decimal(item.received_quantity) > 0 for item in purchase.items):
        blockers.append("recebimento registrado")
    if _active_payable(purchase):
        blockers.append("título a pagar")
    if purchase.status != "negotiating":
        blockers.append(f"etapa {purchase.status}")
    return blockers


def _received_pending_return(item: PurchaseItem) -> Decimal:
    return Decimal(item.received_quantity) - Decimal(item.returned_quantity)


def _deletion_effects(purchase: PurchaseCase) -> str:
    effects: list[str] = [f"{len(purchase.items)} item(ns)"]
    if purchase.quotes:
        effects.append(f"{len(purchase.quotes)} cotação(ões)")
    if purchase.attachments:
        effects.append(f"{len(purchase.attachments)} anexo(s)")
    received = [
        (item, _received_pending_return(item))
        for item in purchase.items
        if _received_pending_return(item) > 0
    ]
    if received:
        quantity = sum((entry[1] for entry in received), Decimal("0"))
        effects.append(
            f"estorno de {quantity:g} unidade(s) recebida(s) em {len(received)} item(ns)"
        )
    payables = [payable for payable in purchase.payables if payable.status != "cancelled"]
    if payables:
        amount = sum((Decimal(payable.amount) for payable in payables), Decimal("0"))
        effects.append(f"título a pagar de {amount:.2f} apagado")
    return "; ".join(effects)


@router.post("/{purchase_id}/cancel", response_model=PurchaseOut)
def cancel_purchase(
    purchase_id: str,
    payload: PurchaseCancelRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PurchaseOut:
    purchase = _load(db, purchase_id, for_update=True)
    if purchase.status == "cancelled":
        raise HTTPException(status_code=409, detail="Esta compra já está cancelada.")
    if purchase.status == "closed":
        raise HTTPException(
            status_code=409, detail="Esta compra já foi encerrada e não tem saldo pendente."
        )
    reason = payload.reason.strip()
    received = [item for item in purchase.items if _pending_return(item) > 0]
    if received and payload.resolution == "return_received":
        _register_returns(db, purchase, payload.return_items, user)
        purchase.status = "cancelled"
        purchase.cancel_reason = reason
        purchase.cancelled_at = datetime.now(UTC)
        purchase.cancelled_by_id = user.id
        _event(
            db,
            purchase,
            "cancelled",
            f"Compra cancelada por {user.full_name} com devolução ao fornecedor. Motivo: {reason}",
            user=user,
        )
    elif received:
        purchase.status = "closed"
        purchase.closed_at = datetime.now(UTC)
        _event(
            db,
            purchase,
            "balance_closed",
            "Saldo pendente encerrado mantendo o material recebido. "
            f"Motivo informado: {reason} · {user.full_name}",
            user=user,
        )
    else:
        purchase.status = "cancelled"
        purchase.cancel_reason = reason
        purchase.cancelled_at = datetime.now(UTC)
        purchase.cancelled_by_id = user.id
        _event(
            db,
            purchase,
            "cancelled",
            f"Compra cancelada por {user.full_name}. Motivo: {reason}",
            user=user,
        )
    _sync_payable(db, purchase, reason=reason)
    db.commit()
    return _present(_load(db, purchase.id), user)


@router.post("/{purchase_id}/close-balance", response_model=PurchaseOut)
def close_purchase_balance(
    purchase_id: str,
    payload: PurchaseCloseRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PurchaseOut:
    purchase = _load(db, purchase_id, for_update=True)
    if purchase.status not in {"ordered", "partially_received"}:
        raise HTTPException(
            status_code=409,
            detail="Só é possível encerrar o saldo de um pedido já enviado ao fornecedor.",
        )
    if not any(Decimal(item.received_quantity) < Decimal(item.quantity) for item in purchase.items):
        raise HTTPException(
            status_code=409, detail="Todos os itens já foram recebidos; não há saldo pendente."
        )
    detail = f"Saldo pendente encerrado por {user.full_name}."
    if payload.reason and payload.reason.strip():
        detail += f" Motivo: {payload.reason.strip()}"
    purchase.status = "closed"
    purchase.closed_at = datetime.now(UTC)
    _event(db, purchase, "balance_closed", detail, user=user)
    _sync_payable(db, purchase)
    db.commit()
    return _present(_load(db, purchase.id), user)


@router.delete("/{purchase_id}", response_model=PurchaseDeletionOut)
def delete_purchase(
    purchase_id: str,
    reason: str | None = Query(default=None, max_length=255),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PurchaseDeletion:
    purchase = _load(db, purchase_id, for_update=True)
    paid = _payable_with_payments(purchase)
    if paid:
        raise HTTPException(
            status_code=409,
            detail=(
                "Este pedido tem pagamento registrado no título a pagar; excluir apagaria "
                "uma saída "
                "de dinheiro já feita. Cancele a compra com estorno para manter o "
                "registro financeiro."
            ),
        )
    for item, quantity in [
        (item, _received_pending_return(item))
        for item in purchase.items
        if _received_pending_return(item) > 0
    ]:
        if not item.product_id:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Vincule {item.sku or item.description} a um produto do catálogo antes de "
                    "estornar o recebimento."
                ),
            )
        move_stock(
            db,
            product_id=item.product_id,
            quantity=-quantity,
            movement_type=MovementType.cancellation,
            reason=f"Estorno da exclusão da compra {purchase.number}",
            reference=purchase.number,
            idempotency_key=f"purchase:{purchase.id}:item:{item.id}:delete:{quantity:f}",
            unit_cost=item.unit_cost,
        )
    db.execute(
        update(MarketStudy)
        .where(MarketStudy.linked_purchase_id == purchase.id)
        .values(linked_purchase_id=None)
    )
    total = (
        Decimal(purchase.expense_amount or 0)
        if purchase.purchase_type == "expense"
        else sum(
            (Decimal(item.quantity) * Decimal(item.unit_cost) for item in purchase.items),
            Decimal("0"),
        )
    )
    children_summary = _deletion_effects(purchase)
    record = PurchaseDeletion(
        purchase_id=purchase.id,
        number=purchase.number,
        purchase_type=purchase.purchase_type,
        supplier_name=purchase.supplier_name,
        items_summary="; ".join(
            f"{Decimal(item.quantity):g} x {item.sku or item.description}"
            for item in purchase.items
        )[:2000]
        or (purchase.expense_category or ""),
        children_summary=children_summary,
        total_amount=Decimal(total).quantize(Decimal("0.01")),
        reason=(reason or "").strip() or None,
        user_id=user.id,
    )
    db.add(record)
    for attachment in purchase.attachments:
        Path(attachment.storage_path).unlink(missing_ok=True)
    db.delete(purchase)
    db.commit()
    return record


@router.patch("/{purchase_id}", response_model=PurchaseOut)
def update_purchase(
    purchase_id: str,
    payload: PurchaseUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PurchaseOut:
    purchase = _load(db, purchase_id, for_update=True)
    payable = _active_payable(purchase)
    if purchase.purchase_type == "expense":
        has_receipts = any(Decimal(item.received_quantity) > 0 for item in purchase.items)
        if purchase.status not in {"ordered", "received", "partially_received"} or has_receipts:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Esta despesa já tem recebimento de material; use as ações de "
                    "encerramento ou cancelamento."
                ),
            )
        if payable and payable.status == "paid":
            raise HTTPException(
                status_code=409,
                detail="Esta despesa já foi paga; use o cancelamento com estorno para corrigir.",
            )
    elif purchase.status != "negotiating":
        raise HTTPException(
            status_code=409,
            detail="Só é possível editar os dados do pedido enquanto a compra está em negociação.",
        )
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("supplier_id"):
        if not db.get(Supplier, changes["supplier_id"]):
            raise HTTPException(status_code=404, detail="Fornecedor não encontrado.")
    for field, value in changes.items():
        setattr(purchase, field, value)
    if {"supplier_id", "supplier_name"} & changes.keys():
        supplier = (
            db.get(Supplier, purchase.supplier_id)
            if purchase.supplier_id
            else (
                db.scalar(select(Supplier).where(Supplier.name == purchase.supplier_name))
                if purchase.supplier_name
                else None
            )
        )
        purchase.supplier = supplier
        _apply_supplier_defaults(purchase, supplier)
    if purchase.purchase_type == "expense":
        _sync_payable(db, purchase)
    _event(db, purchase, "updated", f"Dados do pedido atualizados por {user.full_name}.")
    db.commit()
    return _present(_load(db, purchase.id), user)

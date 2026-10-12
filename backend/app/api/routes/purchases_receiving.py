from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.api.routes.purchases_payables import (
    _sync_payable,
)
from app.api.routes.purchases_support import (
    _event,
    _load,
    _present,
)
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import (
    MovementType,
    Product,
    PurchaseCase,
    PurchaseItem,
    StockMovement,
    User,
)
from app.schemas.common import (
    PurchaseOut,
    PurchaseReceive,
    PurchaseReceiveItem,
)
from app.services.stock import move_stock

router = APIRouter(prefix="/purchases", tags=["Compras"])


def _apply_receipt(
    db: Session,
    purchase: PurchaseCase,
    receipts: list[PurchaseReceiveItem],
    user: User,
) -> PurchaseOut:
    previous_status = purchase.status
    lines = {item.id: item for item in purchase.items}
    for received in receipts:
        item = lines.get(received.item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item não encontrado nesta compra.")
        idempotency_key = f"purchase:{purchase.id}:item:{item.id}:receipt:{received.receipt_id}"
        if db.scalar(
            select(StockMovement.id).where(StockMovement.idempotency_key == idempotency_key)
        ):
            continue
        if item.received_quantity + received.quantity > item.quantity:
            raise HTTPException(
                status_code=409, detail=f"A quantidade recebida excede o pedido para {item.sku}."
            )
        product = (
            db.get(Product, received.product_id)
            if received.product_id
            else (db.get(Product, item.product_id) if item.product_id else None)
        )
        if received.product_id and received.create_product:
            raise HTTPException(
                status_code=422,
                detail="Escolha um produto existente ou cadastre um novo, não ambos.",
            )
        if not product:
            if not received.create_product:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Vincule {item.sku or item.description} a um produto ou marque "
                        "para cadastrá-lo no catálogo."
                    ),
                )
            if not item.sku.strip():
                raise HTTPException(
                    status_code=422,
                    detail="Informe o SKU para cadastrar este material no catálogo.",
                )
            existing = db.scalar(select(Product).where(Product.sku == item.sku))
            if existing:
                product = existing
            else:
                product = Product(
                    sku=item.sku,
                    name=item.description,
                    stock_type="warehouse" if purchase.purchase_type == "expense" else "product",
                    sale_price=0,
                    cost_price=item.unit_cost,
                    current_stock=0,
                    minimum_stock=0,
                    attributes={},
                    fitments=[],
                    images=[],
                )
                db.add(product)
                db.flush()
            item.product_id = product.id
        elif item.product_id and product.id != item.product_id:
            raise HTTPException(
                status_code=409,
                detail=(
                    "O produto vinculado a este item não pode ser trocado "
                    "após o primeiro recebimento."
                ),
            )
        if purchase.purchase_type == "expense" and product.stock_type != "warehouse":
            raise HTTPException(
                status_code=422,
                detail="Recebimentos de despesas só podem creditar itens do almoxarifado.",
            )

        new_received = item.received_quantity + received.quantity
        move_stock(
            db,
            product_id=product.id,
            quantity=received.quantity,
            movement_type=MovementType.purchase_received,
            reason=f"Recebimento da compra {purchase.number}",
            reference=purchase.number,
            idempotency_key=idempotency_key,
            unit_cost=item.unit_cost,
        )
        item.received_quantity = new_received
        _event(
            db,
            purchase,
            "item_received",
            f"{received.quantity:g} {item.unit} de {item.sku or item.description[:80]} "
            f"recebidas por {user.full_name}."
            + (
                f" Observação: {received.observation.strip()}"
                if received.observation and received.observation.strip()
                else ""
            ),
            item=item,
            user=user,
        )

    purchase.status = (
        "received"
        if all(item.received_quantity >= item.quantity for item in purchase.items)
        else "partially_received"
    )
    if purchase.status == "received" and previous_status != "received":
        _event(db, purchase, "received", "Todos os itens foram recebidos e lançados no estoque.")
    _sync_payable(db, purchase)
    db.commit()
    return _present(_load(db, purchase.id), user)


@router.post("/{purchase_id}/receive", response_model=PurchaseOut)
def receive_purchase(
    purchase_id: str,
    payload: PurchaseReceive,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_RECEIVE)),
) -> PurchaseOut:
    purchase = _load(db, purchase_id, for_update=True)
    if purchase.status not in {"ordered", "partially_received", "received"}:
        raise HTTPException(
            status_code=409,
            detail="Só é possível receber itens de um pedido enviado ao fornecedor.",
        )
    return _apply_receipt(db, purchase, payload.items, user)


@router.post("/{purchase_id}/receive-all", response_model=PurchaseOut)
def receive_purchase_in_full(
    purchase_id: str,
    observation: str | None = Query(default=None, max_length=160),
    create_products: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_RECEIVE)),
) -> PurchaseOut:
    purchase = _load(db, purchase_id, for_update=True)
    if purchase.status not in {"ordered", "partially_received"}:
        raise HTTPException(
            status_code=409,
            detail="Só é possível receber itens de um pedido enviado ao fornecedor.",
        )
    receipt_id = uuid4().hex[:24]
    pending = [
        PurchaseReceiveItem(
            item_id=item.id,
            receipt_id=receipt_id,
            quantity=Decimal(item.quantity) - Decimal(item.received_quantity),
            create_product=create_products,
            observation=observation,
        )
        for item in purchase.items
        if Decimal(item.quantity) - Decimal(item.received_quantity) > 0
    ]
    if not pending:
        raise HTTPException(status_code=409, detail="Todos os itens já foram recebidos.")
    return _apply_receipt(db, purchase, pending, user)


def _pending_return(item: PurchaseItem) -> Decimal:
    return Decimal(item.received_quantity) - Decimal(item.returned_quantity)


def _register_returns(
    db: Session,
    purchase: PurchaseCase,
    requested: list,
    user: User,
) -> None:
    """Write the documented stock-out when received goods go back to the supplier."""
    lines = {item.id: item for item in purchase.items}
    pending = {
        item.id: _pending_return(item) for item in purchase.items if _pending_return(item) > 0
    }
    entries = requested or [None]
    registered = 0
    for entry in entries:
        item_id = entry.item_id if entry else None
        if entry is None:
            candidates = [(lines[key], pending[key], None) for key in pending]
        else:
            item = lines.get(item_id)
            if not item:
                raise HTTPException(status_code=404, detail="Item não encontrado nesta compra.")
            candidates = [(item, Decimal(entry.quantity), entry.observation)]
        for item, quantity, observation in candidates:
            quantity = Decimal(quantity)
            if quantity <= 0:
                continue
            if quantity > pending.get(item.id, Decimal("0")):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"A devolução de {item.sku or item.description} excede o que foi recebido."
                    ),
                )
            if not item.product_id:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Vincule {item.sku or item.description} a um produto antes de "
                        "registrar a devolução."
                    ),
                )
            target = Decimal(item.returned_quantity) + quantity
            move_stock(
                db,
                product_id=item.product_id,
                quantity=-quantity,
                movement_type=MovementType.cancellation,
                reason=f"Devolução ao fornecedor na compra {purchase.number}",
                reference=purchase.number,
                idempotency_key=f"purchase:{purchase.id}:item:{item.id}:return:{target:f}",
                unit_cost=item.unit_cost,
            )
            item.returned_quantity = target
            detail = (
                f"{quantity:g} {item.unit} de {item.sku or item.description[:80]} "
                "devolvidas ao fornecedor "
                f"por {user.full_name}."
            )
            if observation and observation.strip():
                detail += f" Observação: {observation.strip()}"
            _event(db, purchase, "item_returned", detail, item=item, user=user)
            registered += 1
    if not registered:
        raise HTTPException(
            status_code=422,
            detail="Informe a quantidade devolvida de pelo menos um item recebido.",
        )

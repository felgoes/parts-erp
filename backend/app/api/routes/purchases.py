from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import (
    MovementType,
    Product,
    PurchaseCase,
    PurchaseEvent,
    PurchaseItem,
    PurchaseQuote,
    StockMovement,
    User,
    UserRole,
)
from app.schemas.common import PurchaseCreate, PurchaseOut, PurchaseQuoteCreate, PurchaseReceive
from app.services.stock import move_stock

router = APIRouter(prefix="/purchases", tags=["Compras"])
MUTATORS = (UserRole.admin, UserRole.manager)


def _event(db: Session, purchase: PurchaseCase, event_type: str, detail: str) -> None:
    db.add(PurchaseEvent(purchase_id=purchase.id, event_type=event_type, detail=detail))


def _load(db: Session, purchase_id: str, *, for_update: bool = False) -> PurchaseCase:
    query = (
        select(PurchaseCase)
        .where(PurchaseCase.id == purchase_id)
        .options(
            selectinload(PurchaseCase.items),
            selectinload(PurchaseCase.quotes),
            selectinload(PurchaseCase.events),
        )
        .execution_options(populate_existing=True)
    )
    if for_update:
        query = query.with_for_update()
    purchase = db.scalar(query)
    if not purchase:
        raise HTTPException(status_code=404, detail="Compra não encontrada")
    return purchase


@router.get("", response_model=list[PurchaseOut])
def list_purchases(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> list[PurchaseCase]:
    return list(
        db.scalars(
            select(PurchaseCase)
            .options(
                selectinload(PurchaseCase.items),
                selectinload(PurchaseCase.quotes),
                selectinload(PurchaseCase.events),
            )
            .order_by(PurchaseCase.created_at.desc())
            .limit(500)
        )
    )


@router.post("", response_model=PurchaseOut, status_code=201)
def create_purchase(
    payload: PurchaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*MUTATORS)),
) -> PurchaseCase:
    for item in payload.items:
        if item.product_id and not db.get(Product, item.product_id):
            raise HTTPException(status_code=404, detail=f"Produto não encontrado: {item.sku}")
    purchase = PurchaseCase(
        number=f"COM-{datetime.now(UTC):%Y}-{uuid4().hex[:6].upper()}",
        status="negotiating",
        needed_by=payload.needed_by,
        notes=payload.notes,
        items=[PurchaseItem(**item.model_dump()) for item in payload.items],
    )
    db.add(purchase)
    db.flush()
    _event(db, purchase, "created", f"Negociação criada por {user.full_name}.")
    db.commit()
    return _load(db, purchase.id)


@router.get("/{purchase_id}", response_model=PurchaseOut)
def get_purchase(
    purchase_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> PurchaseCase:
    return _load(db, purchase_id)


@router.post("/{purchase_id}/quotes", response_model=PurchaseOut)
def add_quote(
    purchase_id: str,
    payload: PurchaseQuoteCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*MUTATORS)),
) -> PurchaseCase:
    purchase = _load(db, purchase_id)
    if purchase.status != "negotiating":
        raise HTTPException(
            status_code=409, detail="As cotações só podem ser registradas durante a negociação."
        )
    expected_item_ids = {item.id for item in purchase.items}
    if set(payload.item_costs) != expected_item_ids:
        raise HTTPException(
            status_code=422,
            detail="Informe o custo unitário desta proposta para todas as peças da negociação.",
        )
    quote_data = payload.model_dump(exclude={"item_costs"})
    quote = PurchaseQuote(
        purchase_id=purchase.id,
        item_costs={item_id: str(cost) for item_id, cost in payload.item_costs.items()},
        **quote_data,
    )
    db.add(quote)
    _event(
        db,
        purchase,
        "quote_received",
        f"Cotação de {quote.supplier_name} registrada por {user.full_name}.",
    )
    db.commit()
    return _load(db, purchase.id)


@router.post("/{purchase_id}/select-quote/{quote_id}", response_model=PurchaseOut)
def select_quote(
    purchase_id: str,
    quote_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*MUTATORS)),
) -> PurchaseCase:
    purchase = _load(db, purchase_id)
    if purchase.status != "negotiating":
        raise HTTPException(
            status_code=409, detail="Esta compra não está mais na etapa de negociação."
        )
    quote = next((q for q in purchase.quotes if q.id == quote_id), None)
    if not quote:
        raise HTTPException(status_code=404, detail="Cotação não encontrada nesta compra.")
    purchase.selected_quote_id = quote.id
    purchase.status = "approved"
    for item in purchase.items:
        item.unit_cost = Decimal(quote.item_costs[item.id])
    _event(
        db,
        purchase,
        "quote_selected",
        f"Cotação de {quote.supplier_name} selecionada por {user.full_name} ({quote.total:.2f}).",
    )
    db.commit()
    return _load(db, purchase.id)


@router.post("/{purchase_id}/place-order", response_model=PurchaseOut)
def place_order(
    purchase_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles(*MUTATORS))
) -> PurchaseCase:
    purchase = _load(db, purchase_id)
    if purchase.status != "approved" or not purchase.selected_quote_id:
        raise HTTPException(
            status_code=409,
            detail="Selecione uma cotação antes de registrar o pedido ao fornecedor.",
        )
    purchase.status = "ordered"
    purchase.ordered_at = datetime.now(UTC)
    _event(db, purchase, "ordered", f"Pedido enviado ao fornecedor por {user.full_name}.")
    db.commit()
    return _load(db, purchase.id)


@router.post("/{purchase_id}/receive", response_model=PurchaseOut)
def receive_purchase(
    purchase_id: str,
    payload: PurchaseReceive,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*MUTATORS)),
) -> PurchaseCase:
    purchase = _load(db, purchase_id, for_update=True)
    if purchase.status not in {"ordered", "partially_received"}:
        raise HTTPException(
            status_code=409,
            detail="Só é possível receber itens de um pedido enviado ao fornecedor.",
        )
    lines = {item.id: item for item in purchase.items}
    for received in payload.items:
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
                        f"Vincule {item.sku} a um produto ou marque para cadastrá-lo no catálogo."
                    ),
                )
            existing = db.scalar(select(Product).where(Product.sku == item.sku))
            if existing:
                product = existing
            else:
                product = Product(
                    sku=item.sku,
                    name=item.description,
                    sale_price=0,
                    cost_price=item.unit_cost,
                    current_stock=0,
                    minimum_stock=0,
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
            f"{received.quantity:g} un. de {item.sku} recebidas por {user.full_name}.",
        )

    purchase.status = (
        "received"
        if all(item.received_quantity >= item.quantity for item in purchase.items)
        else "partially_received"
    )
    if purchase.status == "received":
        _event(db, purchase, "received", "Todos os itens foram recebidos e lançados no estoque.")
    db.commit()
    return _load(db, purchase.id)


@router.post("/{purchase_id}/cancel", response_model=PurchaseOut)
def cancel_purchase(
    purchase_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles(*MUTATORS))
) -> PurchaseCase:
    purchase = _load(db, purchase_id)
    if purchase.status in {"received", "cancelled"}:
        raise HTTPException(
            status_code=409, detail="Uma compra recebida ou já cancelada não pode ser cancelada."
        )
    purchase.status = "cancelled"
    _event(db, purchase, "cancelled", f"Compra cancelada por {user.full_name}.")
    db.commit()
    return _load(db, purchase.id)

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_permission
from app.core.permissions import Permission, has_permission
from app.db.session import get_db
from app.models import (
    MovementType,
    Product,
    PurchaseCase,
    PurchaseAttachment,
    PurchaseEvent,
    PurchaseItem,
    PurchaseQuote,
    StockMovement,
    User,
    UserRole,
)
from app.schemas.common import (
    PurchaseCreate,
    PurchaseItemUpdate,
    PurchaseOut,
    PurchaseQuoteCreate,
    PurchaseReceive,
)
from app.services.stock import move_stock
from app.core.config import get_settings

router = APIRouter(prefix="/purchases", tags=["Compras"])


def _present(purchase: PurchaseCase, user: User) -> PurchaseOut:
    if has_permission(getattr(user, "role", UserRole.admin), Permission.FINANCE_READ):
        return PurchaseOut.model_validate(purchase)
    result = PurchaseOut.model_validate(purchase)
    return result.model_copy(
        update={
            "items": [
                item.model_copy(
                    update={
                        "base_unit_cost": None,
                        "unit_cost": None,
                        "freight_amount": None,
                        "tax_amount": None,
                        "discount_amount": None,
                    }
                )
                for item in result.items
            ],
            "quotes": [
                quote.model_copy(
                    update={
                        "total": None,
                        "item_costs": {},
                        "freight_amount": Decimal("0"),
                        "tax_amount": Decimal("0"),
                        "discount_amount": Decimal("0"),
                    }
                )
                for quote in result.quotes
            ],
            "events": [
                event.model_copy(update={"detail": "Cotação selecionada."})
                if event.event_type == "quote_selected"
                else event
                for event in result.events
            ],
        }
    )


def _event(db: Session, purchase: PurchaseCase, event_type: str, detail: str) -> None:
    db.add(PurchaseEvent(purchase_id=purchase.id, event_type=event_type, detail=detail))


def _line_adjustment(item: PurchaseItem) -> Decimal:
    return item.freight_amount + item.tax_amount - item.discount_amount


def _recompute_purchase_costs(purchase: PurchaseCase, quote: PurchaseQuote | None = None) -> None:
    if not quote:
        for item in purchase.items:
            item.unit_cost = (item.base_unit_cost + _line_adjustment(item) / item.quantity).quantize(Decimal("0.01"))
        return
    adjustment = quote.freight_amount + quote.tax_amount - quote.discount_amount
    subtotal = sum(Decimal(quote.item_costs[item.id]) * item.quantity for item in purchase.items)
    total_quantity = sum(item.quantity for item in purchase.items)
    for item in purchase.items:
        base_cost = Decimal(quote.item_costs[item.id])
        if quote.allocation_method == "quantity" or subtotal <= 0:
            allocated = adjustment * item.quantity / total_quantity
        else:
            allocated = adjustment * (base_cost * item.quantity) / subtotal
        landed_unit_cost = base_cost + (_line_adjustment(item) + allocated) / item.quantity
        if landed_unit_cost < 0:
            raise HTTPException(status_code=422, detail="Os descontos deixam o custo de alguma peça negativo.")
        item.base_unit_cost = base_cost
        item.unit_cost = landed_unit_cost.quantize(Decimal("0.01"))


def _load(db: Session, purchase_id: str, *, for_update: bool = False) -> PurchaseCase:
    query = (
        select(PurchaseCase)
        .where(PurchaseCase.id == purchase_id)
        .options(
            selectinload(PurchaseCase.items),
            selectinload(PurchaseCase.quotes),
            selectinload(PurchaseCase.events),
            selectinload(PurchaseCase.attachments),
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
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_READ)),
) -> list[PurchaseOut]:
    purchases = list(
        db.scalars(
            select(PurchaseCase)
            .options(
                selectinload(PurchaseCase.items),
                selectinload(PurchaseCase.quotes),
                selectinload(PurchaseCase.events),
                selectinload(PurchaseCase.attachments),
            )
            .order_by(PurchaseCase.created_at.desc())
            .limit(500)
        )
    )
    return [_present(purchase, user) for purchase in purchases]


@router.post("", response_model=PurchaseOut, status_code=201)
def create_purchase(
    payload: PurchaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PurchaseOut:
    for item in payload.items:
        if item.product_id and not db.get(Product, item.product_id):
            raise HTTPException(status_code=404, detail=f"Produto não encontrado: {item.sku}")
    purchase = PurchaseCase(
        number=f"COM-{datetime.now(UTC):%Y}-{uuid4().hex[:6].upper()}",
        status="received" if payload.purchase_type == "expense" else "negotiating",
        purchase_type=payload.purchase_type,
        expense_category=payload.expense_category,
        expense_amount=payload.expense_amount,
        supplier_name=payload.supplier_name,
        needed_by=payload.needed_by,
        notes=payload.notes,
        items=[
            PurchaseItem(
                **item.model_dump(),
                base_unit_cost=item.unit_cost,
            )
            for item in payload.items
        ],
    )
    db.add(purchase)
    db.flush()
    _event(db, purchase, "created", f"Negociação criada por {user.full_name}.")
    db.commit()
    return _present(_load(db, purchase.id), user)


@router.post("/{purchase_id}/attachments", response_model=PurchaseOut)
def upload_purchase_attachments(
    purchase_id: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PurchaseOut:
    purchase = _load(db, purchase_id)
    if not files or len(files) > 10:
        raise HTTPException(status_code=422, detail="Envie de 1 a 10 documentos por vez.")
    existing_size = sum(item.size_bytes for item in purchase.attachments)
    base_dir = Path(get_settings().documents_dir).resolve() / "purchases" / purchase.id
    base_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    try:
        for upload in files:
            content = upload.file.read(15 * 1024 * 1024 + 1)
            if not content or len(content) > 15 * 1024 * 1024:
                raise HTTPException(status_code=422, detail="Cada documento deve ter até 15 MB.")
            filename = Path(upload.filename or "documento").name[:255]
            path = (base_dir / f"{uuid4().hex}_{filename}").resolve()
            if base_dir not in path.parents:
                raise HTTPException(status_code=422, detail="Nome de arquivo inválido.")
            path.write_bytes(content)
            saved.append(path)
            db.add(PurchaseAttachment(purchase_id=purchase.id, filename=filename, content_type=upload.content_type or "application/octet-stream", size_bytes=len(content), storage_path=str(path)))
            existing_size += len(content)
        if existing_size > 100 * 1024 * 1024:
            raise HTTPException(status_code=422, detail="O limite total de documentos desta compra é 100 MB.")
        _event(db, purchase, "attachment_added", f"{len(files)} documento(s) anexado(s) por {user.full_name}.")
        db.commit()
    except Exception:
        for path in saved:
            path.unlink(missing_ok=True)
        db.rollback()
        raise
    finally:
        for upload in files:
            upload.file.close()
    return _present(_load(db, purchase.id), user)


@router.get("/{purchase_id}/attachments/{attachment_id}")
def download_purchase_attachment(
    purchase_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.PURCHASE_READ)),
) -> FileResponse:
    attachment = db.scalar(select(PurchaseAttachment).where(PurchaseAttachment.id == attachment_id, PurchaseAttachment.purchase_id == purchase_id))
    if not attachment:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return FileResponse(attachment.storage_path, media_type=attachment.content_type, filename=attachment.filename)


@router.get("/{purchase_id}", response_model=PurchaseOut)
def get_purchase(
    purchase_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_READ)),
) -> PurchaseOut:
    return _present(_load(db, purchase_id), user)


@router.patch("/{purchase_id}/items/{item_id}", response_model=PurchaseOut)
def update_purchase_item(
    purchase_id: str,
    item_id: str,
    payload: PurchaseItemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PurchaseOut:
    purchase = _load(db, purchase_id)
    if purchase.purchase_type != "parts" or purchase.status in {"received", "cancelled"}:
        raise HTTPException(status_code=409, detail="Os custos só podem ser alterados antes da conclusão da compra.")
    item = next((entry for entry in purchase.items if entry.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Peça não encontrada nesta compra.")
    if payload.quantity is not None and payload.quantity < item.received_quantity:
        raise HTTPException(status_code=422, detail="A quantidade não pode ser menor que o já recebido.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "base_unit_cost":
            item.base_unit_cost = value
        elif value is not None:
            setattr(item, field, value)
    selected = next((quote for quote in purchase.quotes if quote.id == purchase.selected_quote_id), None)
    _recompute_purchase_costs(purchase, selected)
    _event(db, purchase, "item_cost_updated", f"Custos de {item.description} atualizados por {user.full_name}.")
    db.commit()
    return _present(_load(db, purchase.id), user)


@router.post("/{purchase_id}/quotes", response_model=PurchaseOut)
def add_quote(
    purchase_id: str,
    payload: PurchaseQuoteCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
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
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
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
    _recompute_purchase_costs(purchase, quote)
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
    purchase_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
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
    user: User = Depends(require_permission(Permission.PURCHASE_RECEIVE)),
) -> PurchaseOut:
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
    return _present(_load(db, purchase.id), user)


@router.post("/{purchase_id}/cancel", response_model=PurchaseOut)
def cancel_purchase(
    purchase_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
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

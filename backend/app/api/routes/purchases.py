from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_permission
from app.core.config import get_settings
from app.core.permissions import Permission, has_permission
from app.db.session import get_db
from app.models import (
    MovementType,
    PayablePayment,
    Product,
    PurchaseAttachment,
    PurchaseCase,
    PurchaseDeletion,
    PurchaseEvent,
    PurchaseItem,
    PurchasePayable,
    PurchaseQuote,
    StockMovement,
    Supplier,
    User,
    UserRole,
)
from app.schemas.common import (
    PayableOut,
    PayableUpdate,
    PurchaseCancelRequest,
    PurchaseCloseRequest,
    PurchaseCreate,
    PurchaseDeletionOut,
    PurchaseItemCreate,
    PurchaseItemUpdate,
    PurchaseOut,
    PurchaseQuoteCreate,
    PurchaseReceive,
    PurchaseReceiveItem,
    PurchaseUpdate,
)
from app.services.purchase_import import analyze_upload
from app.services.payables import payable_balance, refresh_payable
from app.services.stock import move_stock

router = APIRouter(prefix="/purchases", tags=["Compras"])


def _present(purchase: PurchaseCase, user: User) -> PurchaseOut:
    result = PurchaseOut.model_validate(purchase)
    if has_permission(getattr(user, "role", UserRole.admin), Permission.FINANCE_READ):
        return result.model_copy(update={"total_amount": _purchase_total(purchase)})
    return result.model_copy(
        update={
            "total_amount": None,
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


def _purchase_total(purchase: PurchaseCase) -> Decimal:
    if purchase.purchase_type == "expense":
        return Decimal(purchase.expense_amount or 0).quantize(Decimal("0.01"))
    return sum(
        (Decimal(item.quantity) * Decimal(item.unit_cost or 0) for item in purchase.items),
        Decimal("0"),
    ).quantize(Decimal("0.01"))


def _apply_supplier_defaults(purchase: PurchaseCase, supplier: Supplier | None) -> None:
    """Reuse the supplier's usual lead time when the buyer did not set a date."""
    if supplier and supplier.default_delivery_days and not purchase.needed_by:
        purchase.needed_by = datetime.now(UTC) + timedelta(days=supplier.default_delivery_days)


def _event(
    db: Session,
    purchase: PurchaseCase,
    event_type: str,
    detail: str,
    *,
    item: PurchaseItem | None = None,
    user: User | None = None,
) -> None:
    db.add(PurchaseEvent(
        purchase_id=purchase.id,
        item_id=item.id if item else None,
        user_id=user.id if user else None,
        event_type=event_type,
        detail=detail,
    ))


def _line_adjustment(item: PurchaseItem) -> Decimal:
    if Decimal(item.discount_percent or 0) > 0:
        item.discount_amount = (
            Decimal(item.base_unit_cost) * Decimal(item.quantity) * Decimal(item.discount_percent) / 100
        ).quantize(Decimal("0.01"))
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


PAYABLE_TERM_DAYS = 30


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _payable_due_date(purchase: PurchaseCase) -> datetime:
    base = _as_utc(purchase.needed_by) or _as_utc(purchase.document_date) or _as_utc(purchase.created_at) or datetime.now(UTC)
    return base + timedelta(days=PAYABLE_TERM_DAYS)


def _received_value(purchase: PurchaseCase) -> Decimal:
    total = Decimal("0")
    for item in purchase.items:
        net = Decimal(item.received_quantity) - Decimal(item.returned_quantity)
        if net > 0:
            total += net * Decimal(item.unit_cost)
    return total.quantize(Decimal("0.01"))


def _active_payable(purchase: PurchaseCase) -> PurchasePayable | None:
    for payable in purchase.payables:
        if payable.status != "cancelled":
            return payable
    return None


def _sync_payable(
    db: Session,
    purchase: PurchaseCase,
    *,
    reason: str | None = None,
) -> PurchasePayable | None:
    """Keep the accounts payable title aligned with what the purchase actually owes."""
    amount = (
        Decimal(purchase.expense_amount or 0)
        if purchase.purchase_type == "expense"
        else _received_value(purchase)
    )
    payable = _active_payable(purchase)
    if purchase.status == "cancelled":
        if payable and payable.status != "cancelled":
            payable.status = "cancelled"
            payable.cancelled_at = datetime.now(UTC)
            payable.cancel_reason = (reason or purchase.cancel_reason or "")[:255] or None
            _event(db, purchase, "payable_cancelled", f"Título a pagar de {payable.amount:.2f} encerrado com o cancelamento.")
        return payable
    if amount <= 0:
        if payable and payable.status in {"open", "partial"} and not payable.payments:
            payable.status = "cancelled"
            payable.cancelled_at = datetime.now(UTC)
            payable.cancel_reason = "Sem valor a pagar depois do encerramento do saldo."
            _event(db, purchase, "payable_cancelled", "Título a pagar encerrado por não haver valor recebido.")
        elif payable:
            refresh_payable(payable)
        return payable
    if payable:
        if payable.status == "open" and Decimal(payable.amount) != amount:
            payable.amount = amount
            payable.due_date = _payable_due_date(purchase)
        refresh_payable(payable)
        return payable
    payable = PurchasePayable(
        supplier_id=purchase.supplier_id,
        supplier_name=purchase.supplier_name or (purchase.supplier.name if purchase.supplier else None),
        amount=amount,
        due_date=_payable_due_date(purchase),
        status="open",
    )
    purchase.payables.append(payable)
    db.flush()
    _event(db, purchase, "payable_created", f"Título a pagar de {amount:.2f} criado.")
    return payable


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


@router.get("", response_model=list[PurchaseOut])
def list_purchases(
    limit: int = Query(default=500, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
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
            .offset(offset)
            .limit(limit)
        )
    )
    return [_present(purchase, user) for purchase in purchases]


@router.post("", response_model=PurchaseOut, status_code=201)
def create_purchase(
    payload: PurchaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PurchaseOut:
    if payload.source_import_id:
        if not (payload.notes or "").startswith("Importação de documento."):
            raise HTTPException(status_code=422, detail="Identificador de importação inválido.")
        existing = db.scalar(
            select(PurchaseCase).where(PurchaseCase.source_import_id == payload.source_import_id)
        )
        if existing:
            return _present(_load(db, existing.id), user)
    for item in payload.items:
        if item.product_id and not db.get(Product, item.product_id):
            raise HTTPException(status_code=404, detail=f"Produto não encontrado: {item.sku}")
        if item.product_id and payload.purchase_type == "expense":
            product = db.get(Product, item.product_id)
            if product and product.stock_type != "warehouse":
                raise HTTPException(status_code=422, detail="Materiais de despesas devem ser vinculados a itens do almoxarifado.")
    supplier: Supplier | None = None
    if payload.supplier_id:
        supplier = db.get(Supplier, payload.supplier_id)
        if not supplier:
            raise HTTPException(status_code=404, detail="Fornecedor não encontrado.")
    elif payload.supplier_name and payload.supplier_name.strip():
        supplier = db.scalar(
            select(Supplier).where(Supplier.name == payload.supplier_name.strip())
        )
    purchase = PurchaseCase(
        number=f"COM-{datetime.now(UTC):%Y}-{uuid4().hex[:6].upper()}",
        status=("ordered" if payload.items else "received") if payload.purchase_type == "expense" else "negotiating",
        purchase_type=payload.purchase_type,
        expense_category=payload.expense_category,
        expense_amount=payload.expense_amount,
        supplier_name=payload.supplier_name or (supplier.name if supplier else None),
        supplier_id=supplier.id if supplier else None,
        supplier_order_number=payload.supplier_order_number,
        document_date=payload.document_date,
        needed_by=payload.needed_by,
        notes=payload.notes,
        source_import_id=payload.source_import_id,
        items=[
            PurchaseItem(
                **item.model_dump(),
                base_unit_cost=item.unit_cost,
            )
            for item in payload.items
        ],
    )
    _apply_supplier_defaults(purchase, supplier)
    db.add(purchase)
    db.flush()
    _event(db, purchase, "created", f"Compra criada por {user.full_name}.", user=user)
    if payload.purchase_type == "expense":
        _sync_payable(db, purchase)
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
    if purchase.purchase_type != "parts":
        raise HTTPException(status_code=409, detail="Os itens só podem ser alterados em compras de peças.")
    if purchase.status in {"received", "cancelled", "closed"}:
        raise HTTPException(status_code=409, detail="Os itens não podem mais ser alterados nesta etapa.")
    item = next((entry for entry in purchase.items if entry.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Peça não encontrada nesta compra.")
    changes = payload.model_dump(exclude_unset=True)
    if purchase.status not in {"negotiating", "approved"} and {"description", "sku", "unit"} & changes.keys():
        raise HTTPException(
            status_code=409,
            detail="Descrição, SKU e unidade só podem ser alterados antes do pedido ao fornecedor.",
        )
    if payload.quantity is not None and payload.quantity < item.received_quantity:
        raise HTTPException(status_code=422, detail="A quantidade não pode ser menor que o já recebido.")
    for field, value in changes.items():
        if field == "base_unit_cost":
            item.base_unit_cost = value
        elif value is not None:
            setattr(item, field, value)
    selected = next((quote for quote in purchase.quotes if quote.id == purchase.selected_quote_id), None)
    _recompute_purchase_costs(purchase, selected)
    if {"description", "sku", "unit"} & changes.keys():
        _event(db, purchase, "item_updated", f"Dados de {item.description} atualizados por {user.full_name}.")
    else:
        _event(db, purchase, "item_cost_updated", f"Custos de {item.description} atualizados por {user.full_name}.")
    db.commit()
    return _present(_load(db, purchase.id), user)


@router.post("/{purchase_id}/items", response_model=PurchaseOut, status_code=201)
def add_purchase_item(
    purchase_id: str,
    payload: PurchaseItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PurchaseOut:
    purchase = _load(db, purchase_id, for_update=True)
    if purchase.purchase_type != "parts":
        raise HTTPException(status_code=409, detail="Itens só podem ser incluídos em compras de peças.")
    if purchase.status != "negotiating":
        raise HTTPException(
            status_code=409, detail="Só é possível incluir itens durante a negociação."
        )
    if len(purchase.items) >= 100:
        raise HTTPException(status_code=422, detail="Esta compra já atingiu o limite de 100 itens.")
    if payload.product_id and not db.get(Product, payload.product_id):
        raise HTTPException(status_code=404, detail=f"Produto não encontrado: {payload.sku}")
    item = PurchaseItem(**payload.model_dump(), base_unit_cost=payload.unit_cost)
    purchase.items.append(item)
    db.flush()
    _recompute_purchase_costs(purchase)
    _event(
        db,
        purchase,
        "item_added",
        f"{item.description} incluída na negociação por {user.full_name}.",
        item=item,
        user=user,
    )
    db.commit()
    return _present(_load(db, purchase.id), user)


@router.delete("/{purchase_id}/items/{item_id}", response_model=PurchaseOut)
def remove_purchase_item(
    purchase_id: str,
    item_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PurchaseOut:
    purchase = _load(db, purchase_id, for_update=True)
    if purchase.purchase_type != "parts":
        raise HTTPException(status_code=409, detail="Itens só podem ser removidos de compras de peças.")
    if purchase.status != "negotiating":
        raise HTTPException(
            status_code=409, detail="Só é possível remover itens durante a negociação."
        )
    item = next((entry for entry in purchase.items if entry.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Peça não encontrada nesta compra.")
    if len(purchase.items) <= 1:
        raise HTTPException(
            status_code=422,
            detail="A compra precisa de pelo menos uma peça; exclua o rascunho se não for usá-la.",
        )
    if Decimal(item.received_quantity) > 0:
        raise HTTPException(status_code=409, detail="Esta peça já tem recebimento registrado.")
    for quote in purchase.quotes:
        costs = dict(quote.item_costs or {})
        if costs.pop(item.id, None) is not None:
            quote.item_costs = costs
    description = item.description
    purchase.items.remove(item)
    db.flush()
    _recompute_purchase_costs(purchase)
    _event(
        db,
        purchase,
        "item_removed",
        f"{description} removida da negociação por {user.full_name}.",
        user=user,
    )
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
    return _present(_load(db, purchase.id), user)


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
    return _present(_load(db, purchase.id), user)


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
    missing = [item for item in purchase.items if not item.sku.strip() and not item.product_id]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=(
                "Informe o SKU ou vincule um produto antes de enviar o pedido: "
                + ", ".join(item.description[:60] for item in missing[:5])
            ),
        )
    purchase.status = "ordered"
    purchase.ordered_at = datetime.now(UTC)
    _event(db, purchase, "ordered", f"Pedido enviado ao fornecedor por {user.full_name}.")
    db.commit()
    return _present(_load(db, purchase.id), user)


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
                        f"Vincule {item.sku or item.description} a um produto ou marque para cadastrá-lo no catálogo."
                    ),
                )
            if not item.sku.strip():
                raise HTTPException(status_code=422, detail="Informe o SKU para cadastrar este material no catálogo.")
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
            raise HTTPException(status_code=422, detail="Recebimentos de despesas só podem creditar itens do almoxarifado.")

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
            f"{received.quantity:g} {item.unit} de {item.sku or item.description[:80]} recebidas por {user.full_name}."
            + (f" Observação: {received.observation.strip()}" if received.observation and received.observation.strip() else ""),
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
    pending = {item.id: _pending_return(item) for item in purchase.items if _pending_return(item) > 0}
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
                    detail=f"A devolução de {item.sku or item.description} excede o que foi recebido.",
                )
            if not item.product_id:
                raise HTTPException(
                    status_code=422,
                    detail=f"Vincule {item.sku or item.description} a um produto antes de registrar a devolução.",
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
                f"{quantity:g} {item.unit} de {item.sku or item.description[:80]} devolvidas ao fornecedor "
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
        _event(db, purchase, "cancelled", f"Compra cancelada por {user.full_name}. Motivo: {reason}", user=user)
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
    blockers = _delete_blockers(purchase)
    if blockers:
        raise HTTPException(
            status_code=409,
            detail=(
                "Só é possível excluir uma compra em rascunho sem efeitos. "
                f"Impedimentos: {', '.join(blockers)}."
            ),
        )
    total = (
        Decimal(purchase.expense_amount or 0)
        if purchase.purchase_type == "expense"
        else sum((Decimal(item.quantity) * Decimal(item.unit_cost) for item in purchase.items), Decimal("0"))
    )
    record = PurchaseDeletion(
        purchase_id=purchase.id,
        number=purchase.number,
        purchase_type=purchase.purchase_type,
        supplier_name=purchase.supplier_name,
        items_summary="; ".join(
            f"{Decimal(item.quantity):g} x {item.sku or item.description}" for item in purchase.items
        )[:2000]
        or (purchase.expense_category or ""),
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
                detail="Esta despesa já tem recebimento de material; use as ações de encerramento ou cancelamento.",
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


def _find_payable(purchase: PurchaseCase, payable_id: str) -> PurchasePayable:
    payable = next((entry for entry in purchase.payables if entry.id == payable_id), None)
    if not payable:
        raise HTTPException(status_code=404, detail="Título a pagar não encontrado nesta compra.")
    return payable


@router.patch("/{purchase_id}/payables/{payable_id}", response_model=PayableOut)
def update_payable(
    purchase_id: str,
    payable_id: str,
    payload: PayableUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PayableOut:
    purchase = _load(db, purchase_id, for_update=True)
    payable = _find_payable(purchase, payable_id)
    if payable.status != "open":
        raise HTTPException(
            status_code=409, detail="Somente títulos em aberto podem ser ajustados."
        )
    for field, value in payload.model_dump(exclude_unset=True, exclude={"paid_at"}).items():
        if value is not None:
            setattr(payable, field, value)
    _event(db, purchase, "payable_updated", f"Título a pagar ajustado por {user.full_name}.")
    db.commit()
    return PayableOut.model_validate(_find_payable(_load(db, purchase.id), payable_id))


@router.post("/{purchase_id}/payables/{payable_id}/settle", response_model=PayableOut)
def settle_payable(
    purchase_id: str,
    payable_id: str,
    payload: PayableUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PayableOut:
    purchase = _load(db, purchase_id, for_update=True)
    payable = _find_payable(purchase, payable_id)
    if payable.status == "cancelled":
        raise HTTPException(status_code=409, detail="Este título foi encerrado com o cancelamento.")
    balance = payable_balance(payable)
    if balance <= 0:
        raise HTTPException(status_code=409, detail="Este título já está pago.")
    payment = PayablePayment(
        payable_id=payable.id,
        amount=balance,
        paid_at=_as_utc(payload.paid_at) or datetime.now(UTC),
        method=(payload.payment_method or "").strip() or None,
        notes=(payload.payment_notes or "").strip() or None,
        created_by_id=user.id,
    )
    db.add(payment)
    payable.payments.append(payment)
    payable.paid_at = payment.paid_at
    if payment.method:
        payable.payment_method = payment.method
    if payment.notes:
        payable.payment_notes = payment.notes
    db.flush()
    refresh_payable(payable)
    _event(
        db,
        purchase,
        "payable_settled",
        f"Título a pagar de {Decimal(payment.amount):.2f} quitado por {user.full_name}.",
        user=user,
    )
    db.commit()
    return PayableOut.model_validate(_find_payable(_load(db, purchase.id), payable_id))


@router.post("/import-document")
async def import_purchase_document(
    file: UploadFile = File(...),
    profile_id: str | None = None,
    _: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> dict[str, object]:
    try:
        return await analyze_upload(file, profile_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        # Avoid returning or logging document contents or OCR output.
        raise HTTPException(
            status_code=422,
            detail="Não foi possível interpretar o documento. Confira o arquivo e use a compra manual.",
        ) from exc

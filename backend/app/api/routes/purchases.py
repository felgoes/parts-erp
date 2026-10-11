from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_permission
from app.core.config import get_settings
from app.core.permissions import Permission, has_permission
from app.db.session import get_db
from app.models import (
    MovementType,
    MarketStudy,
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
from app.services.payables import apply_payment_condition, normalize_condition, payable_balance, refresh_payable
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
                        "payment_type": None,
                        "installment_count": None,
                        "first_due_days": None,
                        "interval_days": None,
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


def _split_amount(amount: Decimal, weights: dict[str, Decimal]) -> dict[str, Decimal]:
    """Rateia um valor monetário por peso, fechando a sobra de centavos no maior item."""
    total_weight = sum(weights.values(), Decimal("0"))
    if total_weight <= 0:
        return {key: Decimal("0") for key in weights}
    shares = {
        key: (amount * weight / total_weight).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        for key, weight in weights.items()
    }
    residual = (amount - sum(shares.values(), Decimal("0"))).quantize(Decimal("0.01"))
    if residual:
        largest = max(weights, key=lambda key: weights[key])
        shares[largest] = (shares[largest] + residual).quantize(Decimal("0.01"))
    return shares


def _recompute_purchase_costs(purchase: PurchaseCase, quote: PurchaseQuote | None = None) -> None:
    """Aplica no item os valores da cotação vencedora; sem cotação, o custo fica pendente.

    A P9 tirou a digitação de valor da compra: nenhum custo nasce fora da cotação e os
    valores já gravados em compras antigas permanecem exatamente como estão.
    """
    if not quote:
        return
    weights = {
        item.id: item.quantity
        if quote.allocation_method == "quantity"
        else Decimal(quote.item_costs[item.id]) * item.quantity
        for item in purchase.items
    }
    if quote.allocation_method != "quantity" and not any(weight > 0 for weight in weights.values()):
        # Sem preço informado em nenhum item não existe base proporcional: cai para quantidade.
        weights = {item.id: item.quantity for item in purchase.items}
    freight = _split_amount(Decimal(quote.freight_amount), weights)
    tax = _split_amount(Decimal(quote.tax_amount), weights)
    discount = _split_amount(Decimal(quote.discount_amount), weights)
    for item in purchase.items:
        base_cost = Decimal(quote.item_costs[item.id])
        item.freight_amount = freight[item.id]
        item.tax_amount = tax[item.id]
        item.discount_amount = discount[item.id]
        landed = base_cost + (freight[item.id] + tax[item.id] - discount[item.id]) / item.quantity
        if landed < 0:
            raise HTTPException(status_code=422, detail="Os descontos deixam o custo de alguma peça negativo.")
        item.base_unit_cost = base_cost
        item.unit_cost = landed.quantize(Decimal("0.01"))


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


def _owed_value(purchase: PurchaseCase) -> Decimal:
    """Valor devido ao fornecedor.

    P9/P12: a compra de peças deve o valor acordado na cotação vencedora desde a aprovação.
    Quando o saldo pendente é encerrado, o fornecedor não entrega o restante e o título
    passa a valer o que foi efetivamente recebido.
    """
    if purchase.purchase_type == "expense":
        return Decimal(purchase.expense_amount or 0)
    if purchase.status == "closed":
        return _received_value(purchase)
    quote = next((entry for entry in purchase.quotes if entry.id == purchase.selected_quote_id), None)
    if quote is not None:
        return Decimal(quote.total).quantize(Decimal("0.01"))
    return _received_value(purchase)


def _payable_condition(purchase: PurchaseCase) -> tuple[str, int, int, int]:
    """Condição combinada: a da cotação vencedora; sem ela, à vista no prazo padrão."""
    quote = next((entry for entry in purchase.quotes if entry.id == purchase.selected_quote_id), None)
    if quote is not None:
        return (
            quote.payment_type,
            quote.installment_count,
            quote.first_due_days,
            quote.interval_days,
        )
    default_first_due = 0 if purchase.purchase_type == "expense" else PAYABLE_TERM_DAYS
    return "cash", 1, default_first_due, PAYABLE_TERM_DAYS


def _payable_base_date(purchase: PurchaseCase, payable: PurchasePayable | None) -> datetime:
    """P12: data base é a data do documento da compra e, sem ela, a data da aprovação."""
    return (
        _as_utc(purchase.document_date)
        or _as_utc(payable.created_at if payable else None)
        or datetime.now(UTC)
    )


def _apply_payable_condition(
    purchase: PurchaseCase,
    payable: PurchasePayable,
    *,
    condition: tuple[str, int, int, int] | None = None,
) -> None:
    try:
        apply_payment_condition(
            payable,
            base_date=_payable_base_date(purchase, payable),
            condition=condition,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _sync_payable(
    db: Session,
    purchase: PurchaseCase,
    *,
    reason: str | None = None,
    condition: tuple[str, int, int, int] | None = None,
) -> PurchasePayable | None:
    """Keep the accounts payable title aligned with what the purchase actually owes."""
    amount = _owed_value(purchase)
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
        if Decimal(payable.amount) != amount and payable.status in {"open", "partial"}:
            payable.amount = amount
            _apply_payable_condition(purchase, payable)
        elif not payable.installments:
            _apply_payable_condition(purchase, payable, condition=_payable_condition(purchase))
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
    _apply_payable_condition(
        purchase,
        payable,
        condition=normalize_condition(*(condition or _payable_condition(purchase))),
    )
    _event(db, purchase, "payable_created", f"Título a pagar de {amount:.2f} criado.")
    return payable


def _received_pending_return(item: PurchaseItem) -> Decimal:
    return Decimal(item.received_quantity) - Decimal(item.returned_quantity)


def _payable_with_payments(purchase: PurchaseCase) -> PurchasePayable | None:
    for payable in purchase.payables:
        if payable.status != "cancelled" and payable.payments:
            return payable
    return None


def _deletion_effects(purchase: PurchaseCase) -> str:
    effects: list[str] = [f"{len(purchase.items)} item(ns)"]
    if purchase.quotes:
        effects.append(f"{len(purchase.quotes)} cotação(ões)")
    if purchase.attachments:
        effects.append(f"{len(purchase.attachments)} anexo(s)")
    received = [(item, _received_pending_return(item)) for item in purchase.items if _received_pending_return(item) > 0]
    if received:
        quantity = sum((entry[1] for entry in received), Decimal("0"))
        effects.append(f"estorno de {quantity:g} unidade(s) recebida(s) em {len(received)} item(ns)")
    payables = [payable for payable in purchase.payables if payable.status != "cancelled"]
    if payables:
        amount = sum((Decimal(payable.amount) for payable in payables), Decimal("0"))
        effects.append(f"título a pagar de {amount:.2f} apagado")
    return "; ".join(effects)


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
    elif payload.purchase_type == "parts" and any(
        Decimal(item.unit_cost or 0)
        or Decimal(item.freight_amount or 0)
        or Decimal(item.tax_amount or 0)
        or Decimal(item.discount_amount or 0)
        for item in payload.items
    ):
        # P9: a compra de peças nasce sem valor; o custo entra pela cotação ou pela
        # revisão de um documento importado (que tem fonte no papel).
        raise HTTPException(
            status_code=422,
            detail=(
                "Compras de peças são cadastradas sem valor. Informe custo, frete, impostos e "
                "desconto na cotação do fornecedor."
            ),
        )
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
        _sync_payable(
            db,
            purchase,
            condition=(
                payload.payment_type,
                payload.installment_count,
                payload.first_due_days,
                payload.interval_days,
            ),
        )
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
        if value is not None:
            setattr(item, field, value)
    selected = next((quote for quote in purchase.quotes if quote.id == purchase.selected_quote_id), None)
    _recompute_purchase_costs(purchase, selected)
    _event(db, purchase, "item_updated", f"Dados de {item.description} atualizados por {user.full_name}.")
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
    # Peça incluída na negociação entra sem valor: o custo só existe depois da cotação.
    item = PurchaseItem(
        product_id=payload.product_id,
        sku=payload.sku,
        description=payload.description,
        unit=payload.unit,
        quantity=payload.quantity,
        base_unit_cost=Decimal("0"),
    )
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
    if purchase.status not in {"negotiating", "approved"}:
        raise HTTPException(
            status_code=409, detail="As cotações só podem ser registradas antes do pedido ao fornecedor."
        )
    expected_item_ids = {item.id for item in purchase.items}
    if set(payload.item_costs) != expected_item_ids:
        raise HTTPException(
            status_code=422,
            detail="Informe o custo unitário desta proposta para todas as peças da negociação.",
        )
    net_amount = (
        Decimal(payload.total)
        - Decimal(payload.freight_amount)
        - Decimal(payload.tax_amount)
        + Decimal(payload.discount_amount)
    )
    if net_amount < 0:
        raise HTTPException(
            status_code=422,
            detail="O total da proposta é menor que o frete e os impostos menos o desconto.",
        )
    item_subtotal = sum(
        (Decimal(payload.item_costs[item.id]) * item.quantity for item in purchase.items),
        Decimal("0"),
    )
    expected_total = (
        item_subtotal
        + Decimal(payload.freight_amount)
        + Decimal(payload.tax_amount)
        - Decimal(payload.discount_amount)
    )
    if abs(expected_total - Decimal(payload.total)) > Decimal("0.01") * max(1, len(purchase.items)):
        raise HTTPException(
            status_code=422,
            detail=(
                "A soma dos itens não fecha com o total da proposta. "
                "Confira os custos unitários, o frete, os impostos e o desconto."
            ),
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
    if purchase.status not in {"negotiating", "approved"}:
        raise HTTPException(
            status_code=409, detail="Só é possível escolher uma cotação antes de enviar o pedido ao fornecedor."
        )
    quote = next((q for q in purchase.quotes if q.id == quote_id), None)
    if not quote:
        raise HTTPException(status_code=404, detail="Cotação não encontrada nesta compra.")
    purchase.selected_quote_id = quote.id
    purchase.status = "approved"
    _recompute_purchase_costs(purchase, quote)
    # P12: o título a pagar nasce na aprovação, com o valor e a condição da cotação vencedora.
    _sync_payable(db, purchase)
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
    paid = _payable_with_payments(purchase)
    if paid:
        raise HTTPException(
            status_code=409,
            detail=(
                "Este pedido tem pagamento registrado no título a pagar; excluir apagaria uma saída "
                "de dinheiro já feita. Cancele a compra com estorno para manter o registro financeiro."
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
        else sum((Decimal(item.quantity) * Decimal(item.unit_cost) for item in purchase.items), Decimal("0"))
    )
    children_summary = _deletion_effects(purchase)
    record = PurchaseDeletion(
        purchase_id=purchase.id,
        number=purchase.number,
        purchase_type=purchase.purchase_type,
        supplier_name=purchase.supplier_name,
        items_summary="; ".join(
            f"{Decimal(item.quantity):g} x {item.sku or item.description}" for item in purchase.items
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

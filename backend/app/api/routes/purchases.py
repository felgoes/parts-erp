from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_permission
from app.core.config import get_settings
from app.core.permissions import Permission, has_permission
from app.db.session import get_db
from app.models import (
    MarketStudy,
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
    PurchaseImportDocument,
    PurchaseItemCreate,
    PurchaseItemUpdate,
    PurchaseListItem,
    PurchaseListRowItem,
    PurchaseListRowQuote,
    PurchaseOut,
    PurchaseQuoteCreate,
    PurchaseReceive,
    PurchaseReceiveItem,
    PurchaseUpdate,
)
from app.services.payables import (
    apply_payment_condition,
    normalize_condition,
    payable_balance,
    refresh_payable,
)
from app.services.purchase_allocation import (
    MILLI,
    ImportPlan,
    ImportPlanError,
    build_import_plan,
    from_cents,
    half_up_div,
    split_cents,
    to_cents,
    to_milli,
)
from app.services.purchase_import import analyze_upload
from app.services.stock import move_stock

router = APIRouter(prefix="/purchases", tags=["Compras"])


def _mask_costs(result: PurchaseOut, user: User) -> PurchaseOut:
    """Esconde custo, valor de cotação e título de quem não lê financeiro.

    Vale para a lista e para o detalhe.
    """
    if has_permission(getattr(user, "role", UserRole.admin), Permission.FINANCE_READ):
        return result
    # A projeção da lista não carrega custo por item: ali a máscara só precisa esconder o
    # total da cotação, então cada bloco é tratado conforme os campos que realmente existem.
    items = (
        [
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
        ]
        if result.items and hasattr(result.items[0], "unit_cost")
        else result.items
    )
    quotes = [
        quote.model_copy(update={"total": None})
        if not hasattr(quote, "item_costs")
        else quote.model_copy(
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
    ]
    return result.model_copy(
        update={
            "total_amount": None,
            "items": items,
            "quotes": quotes,
            "events": [
                event.model_copy(update={"detail": "Cotação selecionada."})
                if event.event_type == "quote_selected"
                else event
                for event in result.events
            ],
        }
    )


def _present(purchase: PurchaseCase, user: User) -> PurchaseOut:
    result = PurchaseOut.model_validate(purchase)
    if has_permission(getattr(user, "role", UserRole.admin), Permission.FINANCE_READ):
        result = result.model_copy(update={"total_amount": _purchase_total(purchase)})
    return _mask_costs(result, user)


def _present_list_item(purchase: PurchaseCase, user: User) -> PurchaseListItem:
    """Item da lista sem carregar histórico, anexos e títulos — a consulta nem os seleciona."""
    result = PurchaseListItem(
        id=purchase.id,
        number=purchase.number,
        status=purchase.status,
        purchase_type=purchase.purchase_type,
        expense_category=purchase.expense_category,
        expense_amount=purchase.expense_amount,
        supplier_name=purchase.supplier_name,
        supplier_id=purchase.supplier_id,
        supplier_order_number=purchase.supplier_order_number,
        purchase_origin=purchase.purchase_origin,
        document_access_key=purchase.document_access_key,
        document_number=purchase.document_number,
        document_series=purchase.document_series,
        issuer_cnpj=purchase.issuer_cnpj,
        original_currency=purchase.original_currency,
        original_total=purchase.original_total,
        exchange_rate=purchase.exchange_rate,
        paid_amount=purchase.paid_amount,
        document_date=purchase.document_date,
        selected_quote_id=purchase.selected_quote_id,
        needed_by=purchase.needed_by,
        ordered_at=purchase.ordered_at,
        cancel_reason=purchase.cancel_reason,
        cancelled_at=purchase.cancelled_at,
        closed_at=purchase.closed_at,
        notes=purchase.notes,
        created_at=purchase.created_at,
        updated_at=purchase.updated_at,
        items=[
            PurchaseListRowItem(
                id=item.id,
                product_id=item.product_id,
                sku=item.sku,
                description=item.description,
                unit=item.unit,
                quantity=item.quantity,
                received_quantity=item.received_quantity,
            )
            for item in purchase.items
        ],
        quotes=[
            PurchaseListRowQuote(id=quote.id, supplier_name=quote.supplier_name, total=quote.total)
            for quote in purchase.quotes
        ],
        total_amount=_purchase_total(purchase),
    )
    return _mask_costs(result, user)


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
    db.add(
        PurchaseEvent(
            purchase_id=purchase.id,
            item_id=item.id if item else None,
            user_id=user.id if user else None,
            event_type=event_type,
            detail=detail,
        )
    )


def _recompute_purchase_costs(purchase: PurchaseCase, quote: PurchaseQuote | None = None) -> None:
    """Aplica no item os valores da cotação vencedora; sem cotação, o custo fica pendente.

    A P9 tirou a digitação de valor da compra: nenhum custo nasce fora da cotação e os
    valores já gravados em compras antigas permanecem exatamente como estão.

    P0: o rateio roda em inteiros (centavos e milésimos de unidade) pelo mesmo algoritmo
    usado no preview da revisão da importação, para o valor exibido e o gravado fecharem
    centavo a centavo.
    """
    if not quote:
        return
    quantities = {item.id: to_milli(item.quantity) for item in purchase.items}
    base_cents = {item.id: to_cents(quote.item_costs[item.id]) for item in purchase.items}
    proportional = quote.allocation_method != "quantity" and any(
        base_cents[item.id] * quantities[item.id] > 0 for item in purchase.items
    )
    if proportional:
        weights = [(item.id, base_cents[item.id] * quantities[item.id]) for item in purchase.items]
    else:
        # Sem preço informado em nenhum item não existe base proporcional: cai para quantidade.
        weights = [(item.id, quantities[item.id]) for item in purchase.items]
    freight = split_cents(to_cents(quote.freight_amount), weights)
    tax = split_cents(to_cents(quote.tax_amount), weights)
    discount = split_cents(to_cents(quote.discount_amount), weights)
    for item in purchase.items:
        extra_cents = freight[item.id] + tax[item.id] - discount[item.id]
        landed_cents = base_cents[item.id] + half_up_div(extra_cents * MILLI, quantities[item.id])
        if landed_cents < 0:
            raise HTTPException(
                status_code=422, detail="Os descontos deixam o custo de alguma peça negativo."
            )
        item.freight_amount = from_cents(freight[item.id])
        item.tax_amount = from_cents(tax[item.id])
        item.discount_amount = from_cents(discount[item.id])
        item.base_unit_cost = from_cents(base_cents[item.id])
        item.unit_cost = from_cents(landed_cents)


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
    base = (
        _as_utc(purchase.needed_by)
        or _as_utc(purchase.document_date)
        or _as_utc(purchase.created_at)
        or datetime.now(UTC)
    )
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
    quote = next(
        (entry for entry in purchase.quotes if entry.id == purchase.selected_quote_id), None
    )
    if quote is not None:
        return Decimal(quote.total).quantize(Decimal("0.01"))
    return _received_value(purchase)


def _payable_condition(purchase: PurchaseCase) -> tuple[str, int, int, int]:
    """Condição combinada: a da cotação vencedora; sem ela, à vista no prazo padrão."""
    quote = next(
        (entry for entry in purchase.quotes if entry.id == purchase.selected_quote_id), None
    )
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
            _event(
                db,
                purchase,
                "payable_cancelled",
                f"Título a pagar de {payable.amount:.2f} encerrado com o cancelamento.",
            )
        return payable
    if amount <= 0:
        if payable and payable.status in {"open", "partial"} and not payable.payments:
            payable.status = "cancelled"
            payable.cancelled_at = datetime.now(UTC)
            payable.cancel_reason = "Sem valor a pagar depois do encerramento do saldo."
            _event(
                db,
                purchase,
                "payable_cancelled",
                "Título a pagar encerrado por não haver valor recebido.",
            )
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
        supplier_name=purchase.supplier_name
        or (purchase.supplier.name if purchase.supplier else None),
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


def _register_import_document(
    db: Session,
    purchase: PurchaseCase,
    plan: ImportPlan,
    document: PurchaseImportDocument,
    user: User,
) -> None:
    """P0: a compra importada nasce com a cotação do documento aceita e o pedido registrado.

    O documento é a prova de que a compra já foi feita: os valores revisados viram a
    proposta vencedora, o título a pagar nasce na aprovação e o pedido é registrado na
    mesma transação. Nada aqui movimenta estoque.
    """
    quote = PurchaseQuote(
        supplier_name=(purchase.supplier_name or "").strip() or "Fornecedor do documento",
        total=plan.total,
        freight_amount=plan.freight_amount,
        tax_amount=plan.tax_amount,
        discount_amount=plan.discount_amount,
        allocation_method="proportional",
        item_costs={
            item.id: str(line.base_unit_cost)
            for item, line in zip(purchase.items, plan.lines, strict=True)
        },
        # P12, regra 7: à vista, primeiro vencimento em 30 dias corridos da data do documento.
        payment_type="cash",
        installment_count=1,
        first_due_days=PAYABLE_TERM_DAYS,
        interval_days=PAYABLE_TERM_DAYS,
        notes=f"Cotação do documento importado · {document.filename}"[:2000],
    )
    purchase.quotes.append(quote)
    db.flush()
    _event(
        db,
        purchase,
        "quote_received",
        f"Cotação do documento importado de {quote.supplier_name} registrada.",
    )
    purchase.selected_quote_id = quote.id
    purchase.status = "approved"
    _recompute_purchase_costs(purchase, quote)
    _event(db, purchase, "quote_selected", "Cotação do documento aceita na importação.")
    _sync_payable(db, purchase)
    purchase.status = "ordered"
    purchase.ordered_at = datetime.now(UTC)
    _event(
        db,
        purchase,
        "ordered",
        f"Pedido já realizado — registrado na importação do documento por {user.full_name}.",
    )


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


def _pay_purchase_now(
    db: Session,
    purchase: PurchaseCase,
    payload: PurchaseCreate,
    user: User,
) -> None:
    """Compra de marketplace paga no checkout: o título já nasce baixado."""
    amount = (
        Decimal(purchase.expense_amount or 0)
        if purchase.purchase_type == "expense"
        else _purchase_total(purchase)
    )
    if amount <= 0:
        return
    payable = _active_payable(purchase)
    if payable is None:
        payable = PurchasePayable(
            supplier_id=purchase.supplier_id,
            supplier_name=purchase.supplier_name
            or (purchase.supplier.name if purchase.supplier else None),
            amount=amount,
            due_date=_payable_due_date(purchase),
            status="open",
        )
        purchase.payables.append(payable)
        db.flush()
    payment = PayablePayment(
        payable_id=payable.id,
        amount=Decimal(payable.amount),
        paid_at=_as_utc(payload.paid_date) or datetime.now(UTC),
        method=(payload.paid_method or "").strip() or None,
        notes="Pago no checkout da plataforma.",
        created_by_id=user.id,
    )
    payable.payments.append(payment)
    db.flush()
    refresh_payable(payable)
    _event(
        db,
        purchase,
        "payable_settled",
        f"Título a pagar de {Decimal(payable.amount):.2f} quitado no checkout por "
        f"{user.full_name}.",
        user=user,
    )


def _payable_with_payments(purchase: PurchaseCase) -> PurchasePayable | None:
    for payable in purchase.payables:
        if payable.status != "cancelled" and payable.payments:
            return payable
    return None


def _find_duplicate_purchase(db: Session, payload) -> PurchaseCase | None:
    """A chave de acesso identifica o documento fiscal; sem ela, número do pedido + origem."""
    access_key = (payload.document_access_key or "").strip()
    if access_key:
        match = db.scalar(
            select(PurchaseCase).where(PurchaseCase.document_access_key == access_key)
        )
        if match:
            return match
    number = (payload.supplier_order_number or "").strip()
    origin = (payload.purchase_origin or "").strip()
    if number and origin:
        return db.scalar(
            select(PurchaseCase).where(
                PurchaseCase.supplier_order_number == number,
                PurchaseCase.purchase_origin == origin,
            )
        )
    return None


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


@router.get("", response_model=list[PurchaseListItem])
def list_purchases(
    limit: int = Query(default=500, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_READ)),
) -> list[PurchaseListItem]:
    # A lista não carrega histórico, anexos nem títulos: eles só aparecem no detalhe
    # (GET /{id}), então a consulta fica em duas relações e a resposta sem esses blocos.
    purchases = list(
        db.scalars(
            select(PurchaseCase)
            .options(
                selectinload(PurchaseCase.items),
                selectinload(PurchaseCase.quotes),
            )
            .order_by(PurchaseCase.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    return [_present_list_item(purchase, user) for purchase in purchases]


@router.post("", response_model=PurchaseOut, status_code=201)
def create_purchase(
    payload: PurchaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PurchaseOut:
    import_plan = None
    if payload.source_import_id:
        if not (payload.notes or "").startswith("Importação de documento."):
            raise HTTPException(status_code=422, detail="Identificador de importação inválido.")
        existing = db.scalar(
            select(PurchaseCase).where(PurchaseCase.source_import_id == payload.source_import_id)
        )
        if existing:
            return _present(_load(db, existing.id), user)
        # P0: a importação de peças nasce como compra feita (cotação do documento aceita). A
        # importação lançada como despesa (P14) segue o fluxo de despesa mais abaixo.
        if payload.purchase_type == "parts" and not payload.items:
            raise HTTPException(
                status_code=422, detail="Inclua pelo menos uma peça para importar o documento."
            )
        document = payload.import_document if payload.purchase_type == "parts" else None
        if payload.purchase_type == "parts" and document is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Importação sem os dados do documento revisado. Reenvie a revisão com o "
                    "total, frete, impostos e desconto lidos do papel."
                ),
            )
        if document is not None:
            if any(
                Decimal(item.freight_amount or 0)
                or Decimal(item.tax_amount or 0)
                or Decimal(item.discount_amount or 0)
                or Decimal(item.discount_percent or 0)
                for item in payload.items
            ):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Os valores do documento são informados uma única vez, no fechamento da "
                        "importação, e rateados por peça."
                    ),
                )
            missing_identity = [
                item for item in payload.items if not item.sku.strip() and not item.product_id
            ]
            if missing_identity:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Informe o SKU ou vincule um produto antes de enviar o pedido: "
                        + ", ".join(item.description[:60] for item in missing_identity[:5])
                    ),
                )
            try:
                # A compra importada nasce como compra feita — cotação do documento aceita,
                # pedido registrado e título a pagar — e nada é criado se a proposta não fecha.
                import_plan = build_import_plan(
                    [
                        (item.quantity, item.unit_cost, item.line_discount_amount)
                        for item in payload.items
                    ],
                    freight_amount=document.freight_amount,
                    tax_amount=document.tax_amount,
                    discount_amount=document.discount_amount,
                    document_total=document.total,
                )
            except ImportPlanError as error:
                raise HTTPException(status_code=422, detail=str(error)) from error
    elif payload.purchase_type == "parts" and any(
        Decimal(item.unit_cost or 0)
        or Decimal(item.freight_amount or 0)
        or Decimal(item.tax_amount or 0)
        or Decimal(item.discount_amount or 0)
        or Decimal(item.line_discount_amount or 0)
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
                raise HTTPException(
                    status_code=422,
                    detail="Materiais de despesas devem ser vinculados a itens do almoxarifado.",
                )
    supplier: Supplier | None = None
    if payload.supplier_id:
        supplier = db.get(Supplier, payload.supplier_id)
        if not supplier:
            raise HTTPException(status_code=404, detail="Fornecedor não encontrado.")
    elif payload.supplier_name and payload.supplier_name.strip():
        supplier = db.scalar(select(Supplier).where(Supplier.name == payload.supplier_name.strip()))
    duplicate = _find_duplicate_purchase(db, payload)
    if duplicate and duplicate.status != "cancelled":
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    f"Este documento já foi importado na compra {duplicate.number}."
                    " Abra a compra existente ou marque a diferença no documento."
                ),
                "purchase_id": duplicate.id,
                "purchase_number": duplicate.number,
                "purchase_status": duplicate.status,
            },
        )
    purchase = PurchaseCase(
        number=f"COM-{datetime.now(UTC):%Y}-{uuid4().hex[:6].upper()}",
        status=("ordered" if payload.items else "received")
        if payload.purchase_type == "expense"
        else "negotiating",
        purchase_type=payload.purchase_type,
        expense_category=payload.expense_category,
        expense_amount=payload.expense_amount,
        supplier_name=payload.supplier_name or (supplier.name if supplier else None),
        supplier_id=supplier.id if supplier else None,
        supplier_order_number=payload.supplier_order_number,
        purchase_origin=payload.purchase_origin,
        document_access_key=payload.document_access_key,
        document_number=payload.document_number,
        document_series=payload.document_series,
        issuer_cnpj=payload.issuer_cnpj,
        original_currency=payload.original_currency,
        original_total=payload.original_total,
        exchange_rate=payload.exchange_rate,
        paid_amount=payload.paid_amount,
        document_date=payload.document_date,
        needed_by=payload.needed_by,
        notes=payload.notes,
        source_import_id=payload.source_import_id,
        items=[
            PurchaseItem(
                **item.model_dump(exclude={"line_discount_amount"}),
                base_unit_cost=item.unit_cost,
            )
            for item in payload.items
        ],
    )
    _apply_supplier_defaults(purchase, supplier)
    db.add(purchase)
    db.flush()
    _event(db, purchase, "created", f"Compra criada por {user.full_name}.", user=user)
    if import_plan is not None and payload.import_document is not None:
        _register_import_document(db, purchase, import_plan, payload.import_document, user)
    elif payload.purchase_type == "expense":
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
    if payload.paid_now:
        _pay_purchase_now(db, purchase, payload, user)
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
            db.add(
                PurchaseAttachment(
                    purchase_id=purchase.id,
                    filename=filename,
                    content_type=upload.content_type or "application/octet-stream",
                    size_bytes=len(content),
                    storage_path=str(path),
                )
            )
            existing_size += len(content)
        if existing_size > 100 * 1024 * 1024:
            raise HTTPException(
                status_code=422, detail="O limite total de documentos desta compra é 100 MB."
            )
        _event(
            db,
            purchase,
            "attachment_added",
            f"{len(files)} documento(s) anexado(s) por {user.full_name}.",
        )
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
    attachment = db.scalar(
        select(PurchaseAttachment).where(
            PurchaseAttachment.id == attachment_id, PurchaseAttachment.purchase_id == purchase_id
        )
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return FileResponse(
        attachment.storage_path, media_type=attachment.content_type, filename=attachment.filename
    )


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
        raise HTTPException(
            status_code=409, detail="Os itens só podem ser alterados em compras de peças."
        )
    if purchase.status in {"received", "cancelled", "closed"}:
        raise HTTPException(
            status_code=409, detail="Os itens não podem mais ser alterados nesta etapa."
        )
    item = next((entry for entry in purchase.items if entry.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Peça não encontrada nesta compra.")
    changes = payload.model_dump(exclude_unset=True)
    if (
        purchase.status not in {"negotiating", "approved"}
        and {"description", "sku", "unit"} & changes.keys()
    ):
        raise HTTPException(
            status_code=409,
            detail="Descrição, SKU e unidade só podem ser alterados antes do pedido ao fornecedor.",
        )
    if payload.quantity is not None and payload.quantity < item.received_quantity:
        raise HTTPException(
            status_code=422, detail="A quantidade não pode ser menor que o já recebido."
        )
    for field, value in changes.items():
        if value is not None:
            setattr(item, field, value)
    selected = next(
        (quote for quote in purchase.quotes if quote.id == purchase.selected_quote_id), None
    )
    _recompute_purchase_costs(purchase, selected)
    _event(
        db,
        purchase,
        "item_updated",
        f"Dados de {item.description} atualizados por {user.full_name}.",
    )
    db.commit()
    return _present(_load(db, purchase.id), user)


@router.post("/import-document/confirm", response_model=PurchaseOut, status_code=201)
async def confirm_imported_purchase(
    file: UploadFile = File(...),
    payload: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PurchaseOut:
    """Cria a compra importada e anexa o documento original na mesma operação."""
    try:
        data = PurchaseCreate.model_validate_json(payload)
    except ValidationError as error:
        message = " · ".join(
            str(entry.get("msg", "")).strip() for entry in error.errors() if entry.get("msg")
        )[:400]
        raise HTTPException(
            status_code=422, detail=message or "Confira os dados da compra importada."
        ) from error
    purchase = create_purchase(data, db, user)
    stored: Path | None = None
    try:
        content = file.file.read(15 * 1024 * 1024 + 1)
        if not content or len(content) > 15 * 1024 * 1024:
            raise ValueError("O documento deve ter conteúdo e até 15 MB.")
        filename = Path(file.filename or "documento").name[:255]
        base_dir = Path(get_settings().documents_dir).resolve() / "purchases" / purchase.id
        base_dir.mkdir(parents=True, exist_ok=True)
        stored = (base_dir / f"{uuid4().hex}_{filename}").resolve()
        stored.write_bytes(content)
        db.add(
            PurchaseAttachment(
                purchase_id=purchase.id,
                filename=filename,
                content_type=file.content_type or "application/octet-stream",
                size_bytes=len(content),
                storage_path=str(stored),
            )
        )
        _event(
            db,
            _load(db, purchase.id),
            "attachment_added",
            f"Documento original anexado por {user.full_name}.",
            user=user,
        )
        db.commit()
    except Exception:
        db.rollback()
        if stored is not None:
            stored.unlink(missing_ok=True)
        orphan = db.get(PurchaseCase, purchase.id)
        if orphan is not None:
            db.delete(orphan)
            db.commit()
        raise HTTPException(
            status_code=422,
            detail="Não foi possível anexar o documento original; a compra não foi criada.",
        ) from None
    finally:
        file.file.close()
    return _present(_load(db, purchase.id), user)


@router.get("/import-document/duplicates")
def import_document_duplicates(
    document_access_key: str | None = Query(default=None, max_length=44),
    order_number: str | None = Query(default=None, max_length=80),
    origin: str | None = Query(default=None, max_length=40),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> dict[str, object]:
    """Antes de criar a compra, a revisão confere se o documento já entrou no ERP."""
    match: PurchaseCase | None = None
    if document_access_key and document_access_key.strip():
        match = db.scalar(
            select(PurchaseCase).where(
                PurchaseCase.document_access_key == document_access_key.strip()
            )
        )
    if match is None and order_number and order_number.strip() and origin and origin.strip():
        match = db.scalar(
            select(PurchaseCase).where(
                PurchaseCase.supplier_order_number == order_number.strip(),
                PurchaseCase.purchase_origin == origin.strip(),
            )
        )
    if match is None:
        return {"match": None}
    return {
        "match": {
            "purchase_id": match.id,
            "purchase_number": match.number,
            "purchase_status": match.status,
            "cancelled": match.status == "cancelled",
        }
    }


@router.post("/{purchase_id}/items", response_model=PurchaseOut, status_code=201)
def add_purchase_item(
    purchase_id: str,
    payload: PurchaseItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PurchaseOut:
    purchase = _load(db, purchase_id, for_update=True)
    if purchase.purchase_type != "parts":
        raise HTTPException(
            status_code=409, detail="Itens só podem ser incluídos em compras de peças."
        )
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
        raise HTTPException(
            status_code=409, detail="Itens só podem ser removidos de compras de peças."
        )
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
            status_code=409,
            detail="As cotações só podem ser registradas antes do pedido ao fornecedor.",
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
            status_code=409,
            detail="Só é possível escolher uma cotação antes de enviar o pedido ao fornecedor.",
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
            detail=(
                "Não foi possível interpretar o documento. Confira o arquivo e use a compra manual."
            ),
        ) from exc

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.permissions import Permission, has_permission
from app.models import (
    PurchaseCase,
    PurchaseEvent,
    PurchaseItem,
    PurchaseQuote,
    Supplier,
    User,
    UserRole,
)
from app.schemas.common import (
    PurchaseOut,
)
from app.services.purchase_allocation import (
    MILLI,
    from_cents,
    half_up_div,
    split_cents,
    to_cents,
    to_milli,
)

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

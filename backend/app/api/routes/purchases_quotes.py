from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.api.routes.purchases_payables import (
    _sync_payable,
)
from app.api.routes.purchases_support import (
    _event,
    _load,
    _present,
    _recompute_purchase_costs,
)
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import (
    PurchaseCase,
    PurchaseQuote,
    User,
)
from app.schemas.common import (
    PurchaseOut,
    PurchaseQuoteCreate,
)

router = APIRouter(prefix="/purchases", tags=["Compras"])


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
        - Decimal(payload.extras_amount)
        + Decimal(payload.discount_amount)
    )
    if net_amount < 0:
        raise HTTPException(
            status_code=422,
            detail=(
                "O total da proposta é menor que o frete, os impostos e as taxas extras "
                "menos o desconto."
            ),
        )
    item_subtotal = sum(
        (Decimal(payload.item_costs[item.id]) * item.quantity for item in purchase.items),
        Decimal("0"),
    )
    expected_total = (
        item_subtotal
        + Decimal(payload.freight_amount)
        + Decimal(payload.tax_amount)
        + Decimal(payload.extras_amount)
        - Decimal(payload.discount_amount)
    )
    if abs(expected_total - Decimal(payload.total)) > Decimal("0.01") * max(1, len(purchase.items)):
        raise HTTPException(
            status_code=422,
            detail=(
                "A soma dos itens não fecha com o total da proposta. "
                "Confira os custos unitários, o frete, os impostos, as taxas extras e o desconto."
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

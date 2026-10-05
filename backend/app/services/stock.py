from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MovementType, Product, StockMovement


def move_stock(
    db: Session,
    *,
    product_id: str,
    quantity: Decimal,
    movement_type: MovementType,
    reason: str,
    reference: str | None,
    idempotency_key: str,
    unit_cost: Decimal | None = None,
) -> StockMovement:
    existing = db.scalar(
        select(StockMovement).where(StockMovement.idempotency_key == idempotency_key)
    )
    if existing:
        return existing

    product = db.scalar(select(Product).where(Product.id == product_id).with_for_update())
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    new_balance = Decimal(product.current_stock) + Decimal(quantity)
    if new_balance < 0:
        raise HTTPException(
            status_code=409,
            detail=f"Estoque insuficiente para {product.sku}. Disponível: {product.current_stock}",
        )
    valuation_cost = Decimal(unit_cost if unit_cost is not None else product.cost_price)
    movement_value = (abs(Decimal(quantity)) * valuation_cost).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    if movement_type == MovementType.purchase_received and quantity > 0 and new_balance > 0:
        old_value = Decimal(product.current_stock) * Decimal(product.cost_price)
        received_value = Decimal(quantity) * valuation_cost
        product.cost_price = ((old_value + received_value) / new_balance).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    product.current_stock = new_balance
    movement = StockMovement(
        product_id=product.id,
        movement_type=movement_type,
        quantity=quantity,
        balance_after=new_balance,
        unit_cost=valuation_cost,
        movement_value=movement_value,
        reason=reason,
        reference=reference,
        idempotency_key=idempotency_key,
    )
    db.add(movement)
    db.flush()
    return movement

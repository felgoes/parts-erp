from decimal import Decimal

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
    product.current_stock = new_balance
    movement = StockMovement(
        product_id=product.id,
        movement_type=movement_type,
        quantity=quantity,
        balance_after=new_balance,
        reason=reason,
        reference=reference,
        idempotency_key=idempotency_key,
    )
    db.add(movement)
    db.flush()
    return movement

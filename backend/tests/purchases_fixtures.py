from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.api.routes.purchases import (
    add_quote,
    create_purchase,
    place_order,
    select_quote,
)
from app.schemas.common import (
    PurchaseCreate,
    PurchaseItemCreate,
    PurchaseOut,
    PurchaseQuoteCreate,
)


def _actor() -> SimpleNamespace:
    """Route functions take the authenticated user; tests only need id and name."""
    return SimpleNamespace(id="user-qa", full_name="QA")


def _ordered_purchase(db: Session, user: SimpleNamespace) -> PurchaseOut:
    purchase = create_purchase(
        PurchaseCreate(
            supplier_name="Fornecedor A",
            supplier_order_number="PED-123",
            items=[
                PurchaseItemCreate(
                    sku="LR174890",
                    description="Kit membrana Tiggo",
                    quantity=5,
                )
            ],
        ),
        db,
        user,
    )
    line = purchase.items[0]
    purchase = add_quote(
        purchase.id,
        PurchaseQuoteCreate(
            supplier_name="Fornecedor A",
            total=130,
            delivery_days=12,
            item_costs={line.id: Decimal("26")},
        ),
        db,
        user,
    )
    purchase = select_quote(purchase.id, purchase.quotes[0].id, db, user)
    return place_order(purchase.id, db, user)

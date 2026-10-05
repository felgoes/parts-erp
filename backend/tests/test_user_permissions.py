from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes.products import list_products
from app.api.routes.purchases import _present
from app.api.routes.users import update_user
from app.core.permissions import Permission, has_permission
from app.models import Product, PurchaseCase, PurchaseItem, PurchaseQuote, User, UserRole
from app.schemas.common import UserUpdate


def test_operational_profiles_follow_least_privilege() -> None:
    assert has_permission(UserRole.operator, Permission.INVOICE_CREATE)
    assert not has_permission(UserRole.operator, Permission.INVENTORY_ADJUST)
    assert not has_permission(UserRole.operator, Permission.FINANCE_READ)

    assert has_permission(UserRole.stock, Permission.PURCHASE_RECEIVE)
    assert has_permission(UserRole.stock, Permission.INVENTORY_ADJUST)
    assert not has_permission(UserRole.stock, Permission.FINANCE_READ)
    assert not has_permission(UserRole.stock, Permission.PRODUCT_MANAGE)

    assert has_permission(UserRole.finance, Permission.FINANCE_READ)
    assert has_permission(UserRole.finance, Permission.INVOICE_READ)
    assert not has_permission(UserRole.finance, Permission.INVOICE_CREATE)

    assert has_permission(UserRole.viewer, Permission.INVOICE_READ)
    assert not has_permission(UserRole.viewer, Permission.INVOICE_CONFIRM)
    assert not has_permission(UserRole.viewer, Permission.INTEGRATION_CONFIG)

    assert not has_permission(UserRole.manager, Permission.USERS_MANAGE)
    assert not has_permission(UserRole.manager, Permission.INTEGRATION_CONFIG)
    assert has_permission(UserRole.manager, Permission.PRODUCT_MANAGE)


def test_cannot_remove_the_last_active_administrator(db) -> None:
    admin = User(
        id="admin-1",
        email="admin@example.com",
        full_name="Admin",
        password_hash="test-hash",  # noqa: S106
        role=UserRole.admin,
        active=True,
    )
    db.add(admin)
    db.commit()

    with pytest.raises(HTTPException) as raised:
        update_user(admin.id, UserUpdate(active=False), db, admin)

    assert raised.value.status_code == 409
    assert db.get(User, admin.id).active is True


def test_second_administrator_can_be_deactivated_if_one_remains(db) -> None:
    actor = User(
        id="admin-1",
        email="admin@example.com",
        full_name="Admin",
        password_hash="test-hash",  # noqa: S106
        role=UserRole.admin,
        active=True,
    )
    target = User(
        id="admin-2",
        email="other@example.com",
        full_name="Other admin",
        password_hash="test-hash",  # noqa: S106
        role=UserRole.admin,
        active=True,
    )
    db.add_all([actor, target])
    db.commit()

    result = update_user(target.id, UserUpdate(active=False), db, actor)

    assert result.active is False


def test_purchase_costs_are_redacted_for_stock_profile() -> None:
    now = datetime.now(UTC)
    purchase = PurchaseCase(
        id="purchase-1",
        number="COM-2026-ABC123",
        status="ordered",
        created_at=now,
        updated_at=now,
        items=[
            PurchaseItem(
                id="item-1",
                purchase_id="purchase-1",
                sku="PART-1",
                description="Peça de teste",
                quantity=Decimal("2"),
                received_quantity=Decimal("0"),
                unit_cost=Decimal("25.00"),
            )
        ],
        quotes=[
            PurchaseQuote(
                id="quote-1",
                purchase_id="purchase-1",
                supplier_name="Fornecedor",
                total=Decimal("50.00"),
                item_costs={"item-1": "25.00"},
                created_at=now,
                updated_at=now,
            )
        ],
        events=[],
    )

    stock_view = _present(purchase, SimpleNamespace(role=UserRole.stock))
    manager_view = _present(purchase, SimpleNamespace(role=UserRole.manager))

    assert stock_view.items[0].unit_cost is None
    assert stock_view.quotes[0].total is None
    assert stock_view.quotes[0].item_costs == {}
    assert manager_view.items[0].unit_cost == Decimal("25.00")


def test_product_cost_is_redacted_from_stock_product_listing(db) -> None:
    db.add(
        Product(
            id="product-1",
            sku="PART-1",
            name="Peça de teste",
            sale_price=Decimal("80.00"),
            cost_price=Decimal("25.00"),
            current_stock=3,
            minimum_stock=0,
        )
    )
    db.commit()

    stock_view = list_products(None, False, 100, db, User(role=UserRole.stock))
    manager_view = list_products(None, False, 100, db, User(role=UserRole.manager))

    assert stock_view[0].cost_price is None
    assert manager_view[0].cost_price == Decimal("25.00")

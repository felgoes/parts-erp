from decimal import Decimal

from app.api.routes.catalog import catalog_products
from app.models import Product
from app.schemas.common import ProductOut


def test_public_catalog_returns_only_active_products_without_internal_cost(db):
    db.add_all(
        [
            Product(
                sku="PUB-1",
                name="Pastilha",
                sale_price=Decimal("10"),
                cost_price=Decimal("5"),
                current_stock=2,
                active=True,
            ),
            Product(
                sku="OFF-1",
                name="Inativo",
                sale_price=Decimal("8"),
                cost_price=Decimal("3"),
                current_stock=2,
                active=False,
            ),
        ]
    )
    db.commit()

    result = catalog_products(limit=48, db=db)

    assert [item.sku for item in result] == ["PUB-1"]
    assert result[0].in_stock is True
    assert not hasattr(result[0], "cost_price")


def test_product_output_normalizes_legacy_empty_attribute_list(db):
    product = Product(
        sku="LEGACY-1",
        name="Produto importado",
        attributes=[],
    )
    db.add(product)
    db.commit()

    result = ProductOut.model_validate(product)

    assert result.attributes == {}

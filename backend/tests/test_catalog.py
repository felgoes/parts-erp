from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.catalog import catalog_products, router
from app.db.session import get_db
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


def test_public_catalog_excludes_warehouse_before_search_and_limit(db):
    db.add_all(
        [
            Product(sku="ALM-1", name="A material", stock_type="warehouse", active=True),
            Product(sku="PEC-1", name="Z peça", stock_type="product", active=True),
            Product(sku="OFF-2", name="Y peça inativa", stock_type="product", active=False),
        ]
    )
    db.commit()

    assert [item.sku for item in catalog_products(limit=1, db=db)] == ["PEC-1"]
    assert catalog_products(search="ALM-1", limit=48, db=db) == []
    assert [item.sku for item in catalog_products(search="PEC-1", limit=48, db=db)] == ["PEC-1"]


def test_public_catalog_search_matches_vehicle_application(db):
    db.add(
        Product(
            sku="SENSOR-1",
            name="Sensor de temperatura",
            stock_type="product",
            active=True,
            fitments=[
                {
                    "make": "Chery",
                    "model": "Tiggo 7",
                    "year_from": 2021,
                    "year_to": 2025,
                    "engine": "1.6",
                    "version": "Pro",
                }
            ],
        )
    )
    db.commit()

    result = catalog_products(search="Tiggo 7 1.6", limit=48, db=db)

    assert [item.sku for item in result] == ["SENSOR-1"]


def test_public_catalog_api_reflects_stock_type_changes(db):
    product = Product(sku="PEC-2", name="Filtro", stock_type="product", active=True)
    db.add(product)
    db.commit()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db

    with TestClient(app) as client:
        response = client.get("/catalog/products", params={"search": "PEC-2"})
        assert response.status_code == 200
        assert [item["sku"] for item in response.json()] == ["PEC-2"]

        product.stock_type = "warehouse"
        db.commit()
        response = client.get("/catalog/products", params={"search": "PEC-2"})
        assert response.status_code == 200
        assert response.json() == []

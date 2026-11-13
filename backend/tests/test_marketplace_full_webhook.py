import asyncio
from contextlib import nullcontext

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.routes.webhooks import _validate_mercadolivre_notification
from app.models import FullInventory, FullOperation, MarketplaceAccount
from app.workers import marketplace_full, settings

TOPIC = "fbm_stock_operations"
RESOURCE = "/stock/fulfillment/operations/123"
STOCK = "/inventories/FULL001/stock/fulfillment?include_attributes=conditions"


def test_full_webhook_refreshes_current_stock_and_deduplicates_movement(db, monkeypatch):
    account = MarketplaceAccount(seller_id="77", active=True, encrypted_access_token="mock")
    db.add(account)
    db.commit()
    monkeypatch.setattr(marketplace_full, "SessionLocal", lambda: nullcontext(db))
    requests = []
    event = {
        "id": "123", "seller_id": 77, "inventory_id": "FULL001",
        "type": "SALE_CONFIRMATION", "detail": {"available_quantity": -2},
        "result": {"available_quantity": 5},
    }
    available = 4

    def get(self, resource):
        requests.append(resource)
        if resource == RESOURCE:
            return event
        assert resource == STOCK
        return {"available_quantity": available, "total": available, "not_available_quantity": 0}

    monkeypatch.setattr(marketplace_full.MercadoLivreClient, "get", get)
    _validate_mercadolivre_notification(TOPIC, RESOURCE, "77")
    asyncio.run(settings.process_mercadolivre_notification({}, TOPIC, RESOURCE, "77"))
    available = 3
    asyncio.run(settings.process_mercadolivre_notification({}, TOPIC, RESOURCE, "77"))
    inventory = db.scalars(select(FullInventory)).one()
    assert inventory.available_quantity == 3
    assert inventory.operations_synced_at is None
    assert db.scalars(select(FullOperation)).one().operation_id == "123"
    assert requests == [RESOURCE, STOCK, RESOURCE, STOCK]

    event["seller_id"] = 78
    available = 0
    asyncio.run(settings.process_mercadolivre_notification({}, TOPIC, RESOURCE, "77"))
    assert requests[-1] == RESOURCE
    db.refresh(inventory)
    assert inventory.available_quantity == 3


@pytest.mark.parametrize("resource", ["/orders/123", RESOURCE + "?seller_id=77", RESOURCE + "/extra"])
def test_full_webhook_only_accepts_stock_operation_resources(resource):
    with pytest.raises(HTTPException, match="Recurso de notificação inválido"):
        _validate_mercadolivre_notification(TOPIC, resource, "77")

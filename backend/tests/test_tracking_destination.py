from app.integrations.mercadolivre import sync as sync_module
from app.integrations.mercadolivre.client import MercadoLivreClient
from app.models import MarketplaceAccount, MarketplaceOrder
from app.services.tracking_destination import format_shipping_destination


def test_formats_mercado_envios_receiver_address():
    shipment = {
        "receiver_address": {
            "address_line": "Rua das Flores 123",
            "neighborhood": {"name": "Centro"},
            "city": {"name": "São Paulo"},
            "state": {"id": "SP"},
            "zip_code": "01001-000",
        }
    }

    assert (
        format_shipping_destination(shipment)
        == "Rua das Flores 123 · Centro · São Paulo - SP · CEP 01001-000"
    )


def test_formats_street_and_number_without_repeating_them():
    shipment = {
        "destination": {
            "address": {
                "street_name": "Avenida Brasil",
                "street_number": "450",
                "complement": "Loja 2",
                "city": "Campinas",
                "state": "SP",
                "postal_code": "13010-111",
            }
        }
    }

    assert (
        format_shipping_destination(shipment)
        == "Avenida Brasil, 450 - Loja 2 · Campinas - SP · CEP 13010-111"
    )


def test_destination_is_optional_and_accepts_a_plain_address():
    assert format_shipping_destination({}) is None
    assert format_shipping_destination({"receiver_address": "Rua direta, 10"}) == (
        "Rua direta, 10"
    )


def test_shipping_sync_persists_destination_metadata(db, monkeypatch):
    account = MarketplaceAccount(
        seller_id="77",
        encrypted_access_token="encrypted",
        token_expires_at=None,
        active=True,
    )
    order = MarketplaceOrder(
        external_order_id="123",
        seller_id="77",
        status="paid",
        payload={},
        shipment_id="555",
    )
    db.add_all([account, order])
    db.commit()

    shipment = {
        "id": 555,
        "status": "ready_to_ship",
        "receiver_address": {
            "address_line": "Rua das Flores 123",
            "city": {"name": "São Paulo"},
            "state": {"id": "SP"},
            "zip_code": "01001-000",
        },
    }
    monkeypatch.setattr(
        MercadoLivreClient,
        "get",
        lambda self, path, **kwargs: shipment if path == "/shipments/555" else [],
    )

    sync_module.sync_shipping_status(db, order, account)

    assert order.payload["_erp_destination_address"] == (
        "Rua das Flores 123 · São Paulo - SP · CEP 01001-000"
    )

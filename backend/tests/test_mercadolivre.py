from app.integrations.mercadolivre.sync import extract_sku, is_paid


def test_extracts_seller_sku() -> None:
    assert extract_sku({"item": {"seller_sku": "ABC-123"}}) == "ABC-123"


def test_extracts_variation_sku() -> None:
    line = {
        "item": {
            "variation_attributes": [
                {"id": "COLOR", "value_name": "Preto"},
                {"id": "SELLER_SKU", "value_name": "VAR-01"},
            ]
        }
    }
    assert extract_sku(line) == "VAR-01"


def test_paid_when_payment_is_approved() -> None:
    assert is_paid({"status": "confirmed", "payments": [{"status": "approved"}]})

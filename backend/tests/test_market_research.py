from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret
from app.models import MarketStudy, Product, PurchaseCase, User, UserRole
from app.schemas.common import MarketStudyCreate
from app.services import market_research


def _user(db: Session) -> User:
    user = User(
        id="research-user",
        email="research@example.test",
        full_name="Analista local",
        password_hash="not-a-real-password-hash",  # noqa: S106 - only a required test fixture field
        role=UserRole.manager,
    )
    db.add(user)
    db.flush()
    return user


def _offer(identifier: str, price: str, title: str, sold: int) -> dict:
    return {
        "id": identifier,
        "title": title,
        "price": price,
        "sold_quantity_lifetime": sold,
        "similarity": 1.0,
        "permalink": f"https://produto.mercadolivre.com.br/{identifier}",
        "seller_id": "seller-public-id",
    }


def test_market_study_calculates_comparable_price_and_margin_without_ai(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _user(db)
    product = Product(
        sku="OEM-77",
        name="Bomba Tiggo",
        cost_price=Decimal("80"),
        current_stock=Decimal("4"),
    )
    db.add(product)
    db.flush()
    monkeypatch.setattr(
        market_research,
        "_mercadolivre_market_data",
        lambda *_: (
            [
                _offer("MLB1", "150", "Bomba de água Tiggo 7 OEM-77", 20),
                _offer("MLB2", "170", "Bomba Tiggo 7 OEM 77", 30),
            ],
            [{"keyword": "Bomba Tiggo 7", "url": "https://lista.mercadolivre.com.br/bomba"}],
            "MLB",
        ),
    )
    payload = MarketStudyCreate(
        search_term="Bomba Tiggo 7",
        sku=product.sku,
        landed_cost=Decimal("70"),
        shipping_cost=Decimal("10"),
        marketplace_fee_pct=Decimal("16"),
        target_margin_pct=Decimal("20"),
    )
    result = market_research.run_study(db, user, payload)

    assert result.status == "completed"
    assert result.provider_used is None
    assert result.result["market_metrics"]["median_price"] == "160.00"
    assert result.result["price_scenario"]["target_price"] == "125.00"
    assert result.result["price_scenario"]["break_even_price"] == "95.24"
    assert result.result["price_scenario"]["market_margin_at_median_pct"] == "34.0"
    assert result.result["market_metrics"]["sold_units_lifetime_in_comparables"] == 50
    assert result.result["internal_sales"]["stock_units"] == "4"
    assert result.result["ai_report"] is None


def test_market_study_ai_connector_uses_encrypted_secret_and_validated_report(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _user(db)
    connector = market_research.save_connector(
        db,
        provider="openai_responses",
        model="model-test",
        base_url=None,
        api_key="secret-test-key",
        enabled=True,
    )
    assert connector.encrypted_api_key != "secret-test-key"
    assert decrypt_secret(connector.encrypted_api_key) == "secret-test-key"
    monkeypatch.setattr(
        market_research,
        "_mercadolivre_market_data",
        lambda *_: ([_offer("MLB1", "150", "Bomba Tiggo 7", 20)], [], "MLB"),
    )
    monkeypatch.setattr(
        market_research._PROVIDERS["openai_responses"],
        "analyze",
        lambda *_: {
            "summary": "Há preço compatível, valide a aplicação.",
            "opportunities": ["Comparar com OEM"],
            "risks": ["Amostra pequena"],
            "next_steps": ["Cotar fornecedor"],
            "confidence": "medium",
        },
    )
    result = market_research.run_study(
        db,
        user,
        MarketStudyCreate(search_term="Bomba Tiggo 7", landed_cost=Decimal("80")),
    )
    assert result.provider_used == "openai_responses"
    assert result.result["ai_report"]["confidence"] == "medium"
    assert result.result["ai_report"]["risks"] == ["Amostra pequena"]


def test_custom_ai_connector_rejects_internal_urls_and_requires_https() -> None:
    for url in ("http://provider.example/v1", "https://127.0.0.1/v1", "https://provider.local/v1"):
        with pytest.raises(ValueError):
            market_research.validate_connector_url("openai_compatible", url)
    assert (
        market_research.validate_connector_url("openai_compatible", "https://ai.example/v1")
        == "https://ai.example/v1"
    )


def test_market_study_rejects_unprofitable_fee_and_margin_combination() -> None:
    with pytest.raises(ValueError, match="somar menos de 100%"):
        MarketStudyCreate(
            search_term="Bomba Tiggo",
            landed_cost=Decimal("80"),
            marketplace_fee_pct=Decimal("70"),
            target_margin_pct=Decimal("30"),
        )


def test_market_study_converts_once_into_purchase_negotiation(db: Session) -> None:
    user = _user(db)
    study = MarketStudy(
        created_by_id=user.id,
        search_term="Bomba Tiggo 7",
        sku="OEM-77",
        landed_cost=Decimal("70"),
        shipping_cost=Decimal("10"),
        target_margin_pct=Decimal("20"),
        marketplace_fee_pct=Decimal("16"),
        status="completed",
        result={},
    )
    db.add(study)
    db.flush()
    first = market_research.convert_study_to_purchase(
        db, study, user, sku="OEM-77", quantity=Decimal("3")
    )
    repeated = market_research.convert_study_to_purchase(
        db, study, user, sku="OEM-77", quantity=Decimal("3")
    )
    assert first.id == repeated.id == study.linked_purchase_id
    assert first.status == "negotiating"
    assert first.items[0].quantity == Decimal("3")
    assert first.items[0].unit_cost == Decimal("80")
    assert db.scalar(select(PurchaseCase).where(PurchaseCase.id == first.id)) is not None

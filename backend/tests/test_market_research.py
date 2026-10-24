from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret
from app.models import MarketplaceConfig, MarketStudy, Product, PurchaseCase, User, UserRole
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
                _offer("MLB2", "170", "Bomba Tiggo 7 OEM-77", 30),
                _offer("MLB3", "160", "Bomba Tiggo 7 OEM-77", 0),
                _offer("MLB4", "160", "Bomba Tiggo 7 OEM-77", 0),
                _offer("MLB5", "160", "Bomba Tiggo 7 OEM-77", 0),
            ],
            [{"keyword": "Bomba Tiggo 7", "url": "https://lista.mercadolivre.com.br/bomba"}],
            "MLB",
        ),
    )
    payload = MarketStudyCreate(
        search_term="Bomba Tiggo 7",
        sku=product.sku,
        oem="OEM-77",
        landed_cost=Decimal("70"),
        shipping_cost=Decimal("10"),
        fixed_fee=Decimal("0"),
        outbound_shipping=Decimal("0"),
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


def test_market_study_without_cost_keeps_price_research_and_explains_margin_gap(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _user(db)
    offers = [
        _offer(f"MLB-{index}", str(100 + index), "Pastilha de freio OEM-ABC123", 1)
        for index in range(5)
    ]
    monkeypatch.setattr(
        market_research,
        "_mercadolivre_market_data",
        lambda *_: (offers, [], "MLB"),
    )
    study = market_research.run_study(
        db,
        user,
        MarketStudyCreate(search_term="Pastilha de freio", oem="ABC123"),
    )
    assert study.result["market_metrics"]["comparable_offers"] == 5
    assert study.result["market_metrics"]["conclusion"] == "Dados insuficientes para estimar margem"
    assert study.result["price_scenario"]["cost_known"] is False
    assert study.result["price_scenario"]["target_price"] is None
    assert "custo de compra" in study.result["price_scenario"]["unknown_components"]


def test_market_study_margin_includes_fixed_fee_and_outbound_shipping(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _user(db)
    offers = [_offer(f"MLB-{index}", "160", "Bomba Tiggo OEM-77", 1) for index in range(5)]
    monkeypatch.setattr(
        market_research,
        "_mercadolivre_market_data",
        lambda *_: (offers, [], "MLB"),
    )
    study = market_research.run_study(
        db,
        user,
        MarketStudyCreate(
            search_term="Bomba Tiggo",
            oem="OEM-77",
            landed_cost=Decimal("70"),
            shipping_cost=Decimal("10"),
            marketplace_fee_pct=Decimal("16"),
            target_margin_pct=Decimal("20"),
            fixed_fee=Decimal("5"),
            outbound_shipping=Decimal("10"),
        ),
    )
    assert study.result["price_scenario"]["target_price"] == "148.44"
    assert study.result["price_scenario"]["market_margin_at_median_pct"] == "24.6"
    assert study.result["price_scenario"]["unknown_components"] == []


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


def test_market_study_uses_company_commission_default_when_not_overridden(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _user(db)
    db.add(MarketplaceConfig(study_default_commission_pct=Decimal("12.5")))
    db.flush()
    offers = [_offer(f"MLB-{index}", "160", "Bomba Tiggo OEM-77", 1) for index in range(5)]
    monkeypatch.setattr(
        market_research,
        "_mercadolivre_market_data",
        lambda *_: (offers, [], "MLB"),
    )
    study = market_research.run_study(
        db,
        user,
        MarketStudyCreate(
            search_term="Bomba Tiggo",
            oem="OEM-77",
            landed_cost=Decimal("70"),
            shipping_cost=Decimal("10"),
            fixed_fee=Decimal("0"),
            outbound_shipping=Decimal("0"),
            target_margin_pct=Decimal("20"),
        ),
    )
    assert study.marketplace_fee_pct == Decimal("12.50")
    assert study.result["price_scenario"]["marketplace_fee_pct"] == "12.50"


def test_offer_compatibility_priority_and_fitment_evidence() -> None:
    classify = market_research._classify_offer
    fitments = [{"make": "Volkswagen", "model": "Tiguan", "year_from": 2020, "year_to": 2022}]
    assert (
        classify(_offer("OEM", "100", "Bomba OEM-1234 Tiguan", 0), "OEM-1234", fitments)
        == "oem_exact"
    )
    assert classify(_offer("CAT", "100", "Bomba Tiguan", 0), None, fitments, {"CAT"}) == "catalog"
    assert (
        classify(_offer("FIT", "100", "Bomba Volkswagen Tiguan 2021", 0), None, fitments)
        == "fitment_confirmed"
    )
    assert classify(_offer("MAYBE", "100", "Bomba automotiva", 0), None, fitments) == "unconfirmed"


def test_unconfirmed_ads_are_excluded_and_small_sample_has_no_conclusion(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _user(db)
    offers = [
        _offer("MLB-OEM-1", "100", "Bomba OEM-1234 Tiguan", 1),
        _offer("MLB-OEM-2", "110", "Bomba OEM-1234 Tiguan", 1),
        *[_offer(f"MLB-UNC-{index}", "90", "Bomba automotiva universal", 1) for index in range(3)],
    ]
    monkeypatch.setattr(
        market_research,
        "_mercadolivre_market_data",
        lambda *_: (offers, [], "MLB"),
    )
    study = market_research.run_study(
        db, user, MarketStudyCreate(search_term="Bomba", oem="OEM-1234")
    )
    metrics = study.result["market_metrics"]
    assert metrics["offers_found"] == 5
    assert metrics["comparable_offers"] == 2
    assert metrics["small_sample"] is True
    assert metrics["conclusion"] == "Poucos anúncios comparáveis"
    assert all(offer["compatibility"] == "unconfirmed" for offer in study.result["offers"][2:])


def test_freeform_refinement_is_searched_as_text_and_zero_results_are_explained(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _user(db)
    observed: dict[str, object] = {}

    def no_results(_db, query, category_id):
        observed.update(query=query, category_id=category_id)
        return [], [], "MLB"

    monkeypatch.setattr(market_research, "_mercadolivre_market_data", no_results)
    study = market_research.run_study(
        db,
        user,
        MarketStudyCreate(search_term="Bomba", category_id="Tiguan 2020"),
    )
    assert observed == {"query": "Bomba Tiguan 2020", "category_id": None}
    assert study.result["market_metrics"]["conclusion"] == "Nenhum anúncio encontrado"

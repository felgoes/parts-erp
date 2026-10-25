import json
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.api.routes.market_studies import _summary
from app.core.security import encrypt_secret
from app.models import Product, User, UserRole
from app.models.assistant import AssistantConfiguration
from app.schemas.company import CompanyProfileData
from app.schemas.market_studies import MarketStudyCreate
from app.schemas.vehicle_market import VehicleMarketImportIn
from app.services import (
    china_suppliers,
    market_opportunity_ai,
    market_opportunity_candidates,
    market_study_opportunity,
    vehicle_market,
)
from app.services.company_profile import empty_company_data, save_company_profile


def _user(db) -> User:
    user = User(
        id="opportunity-user",
        email="opportunity@example.test",
        full_name="Pesquisador",
        password_hash="not-used",  # noqa: S106 - required fixture
        role=UserRole.admin,
    )
    db.add(user)
    db.flush()
    return user


def _company(db, user: User) -> None:
    data = CompanyProfileData.model_validate(empty_company_data())
    data.identification.legal_name = "Empresa Exemplo Ltda."
    data.identification.cnpj = "11222333000181"
    data.identification.registration_status = "ATIVA"
    data.addresses.fiscal.city = "São Paulo"
    data.addresses.fiscal.state = "SP"
    data.contact.business_email = "contato@example.test"
    data.fiscal.tax_regime = "simples_nacional"
    data.market_study.channel_commission_pct = Decimal("16")
    data.market_study.expected_return_pct = Decimal("2")
    save_company_profile(db, user, revision=0, data=data, manual_fields=[])


def _product(db) -> Product:
    product = Product(
        sku="FIAT-OEM-1",
        name="Bomba de água",
        category="Arrefecimento",
        manufacturer_part_number="FIAT-OEM-1",
        cost_price=Decimal("80"),
        fitments=[
            {
                "make": "Fiat",
                "model": "Argo",
                "year_from": 2018,
                "year_to": 2024,
            }
        ],
    )
    db.add(product)
    db.flush()
    return product


def test_study_without_company_profile_is_saved_as_pending(db) -> None:
    user = _user(db)
    study = market_study_opportunity.run_opportunity_study(
        db,
        user,
        MarketStudyCreate(mode="brand", brand="Fiat"),
    )
    assert study.status == "pending_company_profile"
    assert study.result["company_profile_pending"]["completion_url"] == "/settings/empresa"
    assert study.result["candidates"] == []
    assert study.result["company_snapshot"] == {}


def test_opportunity_execution_is_queued_before_external_sources_are_consulted(db) -> None:
    user = _user(db)
    study = market_study_opportunity.queue_opportunity_study(
        db,
        user,
        MarketStudyCreate(mode="nationality", nationality="Itália"),
    )
    assert study.status == "generating"
    assert study.result["request_payload"]["nationality"] == "Itália"
    assert study.result["scope"]["nationality"] == "Itália"


def test_brand_study_uses_company_snapshot_and_explicit_unavailable_china_source(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _user(db)
    _company(db, user)
    _product(db)
    offers = [
        {
            "id": f"MLB{index}",
            "title": "Bomba de água Fiat Argo FIAT-OEM-1",
            "price": str(100 + index),
            "similarity": 1,
            "permalink": f"https://produto.mercadolivre.com.br/MLB{index}",
        }
        for index in range(5)
    ]
    monkeypatch.setattr(
        market_opportunity_candidates,
        "_mercadolivre_market_data",
        lambda *_: (offers, [], "MLB"),
    )
    study = market_study_opportunity.run_opportunity_study(
        db,
        user,
        MarketStudyCreate(mode="brand", brand="Fiat", include_suppliers_china=True),
    )
    assert study.result["scope"]["nationality"] == "Itália"
    assert study.result["company_snapshot"]["fiscal_state"] == "SP"
    assert study.result["company_snapshot"]["profile_version_id"]
    assert study.result["best_candidate"]["sku"] == "FIAT-OEM-1"
    assert study.result["best_candidate"]["decision"] != "recomendada_para_teste"
    assert study.result["supplier_research"]["status"] == "unavailable"
    assert "Nenhum fornecedor" in study.result["supplier_research"]["message"]
    assert study.result["supplier_research"]["leads"] == []
    assert study.result["tax_rules"]["status"] == "unavailable"
    summary = _summary(study)
    assert summary["brand"] == "Fiat"
    assert summary["best_candidate"] == "Arrefecimento"

    data = CompanyProfileData.model_validate(empty_company_data())
    data.identification.legal_name = "Empresa Exemplo Ltda."
    data.identification.cnpj = "11222333000181"
    data.identification.registration_status = "ATIVA"
    data.addresses.fiscal.city = "Belo Horizonte"
    data.addresses.fiscal.state = "MG"
    data.contact.business_email = "contato@example.test"
    data.fiscal.tax_regime = "lucro_real"
    data.market_study.channel_commission_pct = Decimal("10")
    data.market_study.expected_return_pct = Decimal("1")
    save_company_profile(db, user, revision=1, data=data, manual_fields=[])
    assert study.result["company_snapshot"]["fiscal_state"] == "SP"
    assert study.result["company_snapshot"]["tax_regime"] == "simples_nacional"


def test_china_adapters_never_manufacture_a_supplier() -> None:
    unavailable = china_suppliers.UnavailableChinaSupplierProvider().search([])
    fixture = china_suppliers.FixtureChinaSupplierProvider().search([])
    assert unavailable.status == "unavailable"
    assert fixture.status == "unavailable"
    assert not unavailable.leads and not fixture.leads
    assert "Nenhuma empresa" in fixture.message


def test_new_study_reuses_saved_ai_connector_without_overriding_deterministic_decision(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _user(db)
    _company(db, user)
    _product(db)
    db.add(
        AssistantConfiguration(
            id="shared",
            provider="openai_responses",
            model="test-model",
            encrypted_api_key=encrypt_secret("encrypted-test-key"),
        )
    )
    db.flush()
    offers = [
        {
            "id": f"AI-MLB-{index}",
            "title": "Bomba de água Fiat Argo FIAT-OEM-1",
            "price": "120",
            "similarity": 1,
            "permalink": f"https://produto.mercadolivre.com.br/AI-MLB-{index}",
        }
        for index in range(5)
    ]
    monkeypatch.setattr(
        market_opportunity_candidates,
        "_mercadolivre_market_data",
        lambda *_: (offers, [], "MLB"),
    )
    monkeypatch.setattr(
        market_opportunity_ai,
        "complete",
        lambda *args, **kwargs: SimpleNamespace(
            content=json.dumps(
                {
                    "schema_version": "market_opportunity_result.v1",
                    "executive_summary": "Confirme a aplicação antes de cotar.",
                    "ranking": [
                        {
                            "candidate_id": "cand_01",
                            "why": "Há oferta compatível observada.",
                            "facts": ["Cinco anúncios compatíveis."],
                            "hypotheses": [],
                            "missing_data": ["Frete de entrada."],
                            "risks": ["Aplicação ainda não confirmada."],
                            "score": 100,
                            "decision": "recomendada_para_teste",
                        }
                    ],
                    "next_best_action": "Pedir cotação real.",
                    "limitations": ["Preço publicado não é cotação firme."],
                }
            ),
            input_tokens=10,
            output_tokens=20,
        ),
    )

    study = market_study_opportunity.run_opportunity_study(
        db,
        user,
        MarketStudyCreate(mode="brand", brand="Fiat"),
    )

    assert study.provider_used == "openai_responses"
    assert study.result["ai_report"]["provider"] == "openai_responses"
    assert study.result["candidates"][0]["ai_explanation"]["why"]
    assert study.result["candidates"][0]["decision"] != "recomendada_para_teste"
    assert study.result["executive_summary"] == "Confirme a aplicação antes de cotar."


def test_vehicle_market_import_is_idempotent_and_keeps_flow_and_stock_separate(db) -> None:
    payload = VehicleMarketImportIn(
        source="Fonte pública de teste",
        metric="registrations",
        period="2026-09",
        source_url="https://example.test/emplacamentos",
        published_at=datetime(2026, 10, 1, tzinfo=UTC),
        records=[
            {"brand": "Fiat", "model": "Argo", "value": 100},
            {"brand": "Toyota", "model": "Corolla", "value": 80},
        ],
    )
    first = vehicle_market.import_snapshot(db, payload)
    repeated = vehicle_market.import_snapshot(db, payload)
    assert first.id == repeated.id
    overview = vehicle_market.vehicle_market_overview(db)
    assert overview["monthly"]["total"] == 180
    assert overview["ytd"]["total"] == 180
    assert overview["fleet"]["total"] is None
    assert overview["fleet"]["period"] is None
    assert overview["monthly"]["brands"][0] == {
        "label": "Fiat",
        "value": 100,
        "share_pct": 55.56,
    }
    assert overview["sources"][1]["status"] == "unavailable"
    assert overview["sources"][1]["metric"] == "fleet"


def test_vehicle_market_rejects_duplicate_dimensions(db) -> None:
    payload = VehicleMarketImportIn(
        source="Fonte pública de teste",
        metric="fleet",
        period="2026-09",
        source_url="https://example.test/frota",
        records=[
            {"brand": "Fiat", "model": "Argo", "value": 100},
            {"brand": "Fiat", "model": "Argo", "value": 90},
        ],
    )
    with pytest.raises(ValueError, match="duplicadas"):
        vehicle_market.import_snapshot(db, payload)

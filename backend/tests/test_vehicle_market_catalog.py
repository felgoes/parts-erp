from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx

from app.models import VehicleCatalogCache
from app.services import vehicle_market_catalog


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        fipe_market_api_key=None,
        fipe_market_catalog_url="https://catalog.example",
    )


def test_complete_catalog_finds_brand_outside_top_20_and_groups_models(
    db, monkeypatch
) -> None:
    calls = []

    def fetch(url, **kwargs):
        calls.append((url, kwargs.get("params")))
        if url.endswith("/marcas"):
            return _Response(["Fiat", "Peugeot", "Toyota"])
        return _Response(
            [
                "2008 Active 1.0",
                "2008 GT 1.0",
                "208 Active 1.0",
                "Partner Furgão 1.6",
            ]
        )

    monkeypatch.setattr(vehicle_market_catalog, "get_settings", _settings)
    monkeypatch.setattr(vehicle_market_catalog.httpx, "get", fetch)

    brands = vehicle_market_catalog.complete_brands(db)
    peugeot = vehicle_market_catalog.brand_models(db, "peugeot")
    families = vehicle_market_catalog.model_families(peugeot["models"])

    assert brands["data"] == ["Fiat", "Peugeot", "Toyota"]
    assert peugeot["found"] is True
    assert peugeot["brand"] == "Peugeot"
    assert families == [
        {"name": "2008", "versions": 2},
        {"name": "208", "versions": 1},
        {"name": "Partner", "versions": 1},
    ]
    vehicle_market_catalog.brand_models(db, "Peugeot")
    assert len(calls) == 2


def test_catalog_failure_keeps_stale_complete_brand_list(db, monkeypatch) -> None:
    db.add(
        VehicleCatalogCache(
            id="catalog-cache",
            kind="brands",
            cache_key="cars",
            data=["Peugeot"],
            retrieved_at=datetime.now(UTC) - timedelta(days=2),
        )
    )
    db.commit()
    monkeypatch.setattr(vehicle_market_catalog, "get_settings", _settings)
    monkeypatch.setattr(
        vehicle_market_catalog.httpx,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ConnectError("offline")),
    )

    result = vehicle_market_catalog.complete_brands(db)
    assert result["status"] == "stale"
    assert result["data"] == ["Peugeot"]

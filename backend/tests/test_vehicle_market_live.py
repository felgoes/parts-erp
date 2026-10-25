from types import SimpleNamespace

import httpx

from app.services import vehicle_market, vehicle_market_fleet_source, vehicle_market_live


class _Response:
    is_success = True
    status_code = 200

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def json(self) -> dict:
        return self.payload


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        fipe_market_api_key=None,
        fipe_market_api_url="https://market.example/current",
        vehicle_market_cache_hours=6,
    )


def test_live_market_imports_top_models_with_explicit_brand_mapping(
    db, monkeypatch
) -> None:
    calls = 0

    def fetch(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _Response(
            {
                "sucesso": True,
                "referencia": "Outubro/2026",
                "ano": 2026,
                "mes": 10,
                "segmentos": {
                    "auto": {
                        "itens": [
                            {"posicao": 1, "modelo": "ARGO", "unidades": 120},
                            {"posicao": 2, "modelo": "MODELO NOVO", "unidades": 30},
                        ]
                    },
                    "comercial": {
                        "itens": [{"posicao": 1, "modelo": "STRADA", "unidades": 80}]
                    },
                },
            }
        )

    monkeypatch.setattr(vehicle_market_live, "get_settings", _settings)
    monkeypatch.setattr(vehicle_market_live.httpx, "get", fetch)
    first = vehicle_market_live.sync_live_vehicle_market(db)
    second = vehicle_market_live.sync_live_vehicle_market(db)

    assert first["status"] == "updated"
    assert second["status"] == "cached"
    assert calls == 1
    rows = vehicle_market.vehicle_market_overview(
        db, period="2026-10"
    )
    assert rows["monthly"]["total"] == 230
    brands = {row["label"]: row["value"] for row in rows["monthly"]["brands"]}
    assert brands["Fiat"] == 200
    assert brands["Não mapeado"] == 30


def test_live_market_preserves_unavailable_state_without_snapshot(
    db, monkeypatch
) -> None:
    monkeypatch.setattr(vehicle_market_live, "get_settings", _settings)
    monkeypatch.setattr(
        vehicle_market_live.httpx,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ConnectError("offline")),
    )
    result = vehicle_market_live.sync_live_vehicle_market(db)
    assert result["status"] == "unavailable"
    assert "indisponível" in result["message"]


def test_fleet_source_lists_latest_official_publication(monkeypatch) -> None:
    class FleetResponse(_Response):
        def raise_for_status(self) -> None:
            return None

    vehicle_market_fleet_source._cache = None
    monkeypatch.setattr(
        vehicle_market_fleet_source,
        "get_settings",
        lambda: SimpleNamespace(senatran_fleet_package_url="https://data.example/package"),
    )
    monkeypatch.setattr(
        vehicle_market_fleet_source.httpx,
        "get",
        lambda *args, **kwargs: FleetResponse(
            {
                "result": {
                    "resources": [
                        {
                            "format": "ZIP",
                            "created": "2026-09-01",
                            "description": "Frota de Agosto de 2026",
                            "url": "https://data.example/older.zip",
                        },
                        {
                            "format": "ZIP",
                            "created": "2026-10-01",
                            "description": "Frota de Setembro de 2026",
                            "url": "https://data.example/latest.zip",
                        },
                    ]
                }
            }
        ),
    )
    status = vehicle_market_fleet_source.fleet_source_status()
    assert status["status"] == "available"
    assert status["resource_url"] == "https://data.example/latest.zip"
    assert "Setembro" in status["period"]

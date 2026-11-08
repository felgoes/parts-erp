from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.schemas.vehicle_market import VehicleMarketImportIn, VehicleMarketRecordIn
from app.services.vehicle_market import import_snapshot
from app.services.vehicle_market_live import SOURCE, SOURCE_URL


def _publication(db, period, rows, source=SOURCE):
    import_snapshot(
        db,
        VehicleMarketImportIn(
            source=source,
            metric="registrations",
            period=period,
            source_url=SOURCE_URL,
            records=[
                VehicleMarketRecordIn(
                    brand="Marca QA",
                    nationality="QA",
                    model=model,
                    value=value,
                    vehicle_category=category,
                    source_row_label="Campo interno",
                )
                for model, value, category in rows
            ],
        ),
        allow_partial=True,
    )


def test_ranking_exposes_only_the_latest_public_top_twenty_per_segment(db, monkeypatch):
    _publication(db, "2026-04", [("QA Utilitário", 10, "comercial_leve")])
    _publication(
        db, "2026-05", [(f"QA Carro {i}", i, "automovel") for i in range(1, 23)]
    )
    _publication(db, "2026-06", [("Importação manual", 100, "automovel")], "Outra fonte")
    monkeypatch.setitem(app.dependency_overrides, get_db, lambda: db)
    client = TestClient(app)
    path = "/api/v1/catalog/vehicle-ranking"

    result = client.get(path)
    assert result.status_code == 200
    assert result.headers["cache-control"] == "public, max-age=300"
    assert result.json() == {
        "period": "2026-05",
        "source": SOURCE,
        "source_url": SOURCE_URL,
        "items": [{"model": f"QA Carro {i}", "registrations": i} for i in range(22, 2, -1)],
    }
    result = client.get(path, params={"category": "comercial_leve"}).json()
    assert result["period"] == "2026-04"
    assert result["items"] == [{"model": "QA Utilitário", "registrations": 10}]
    assert client.get(path, params={"category": "fleet"}).status_code == 422


def test_ranking_without_publication_returns_empty_items(db, monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_db, lambda: db)
    result = TestClient(app).get("/api/v1/catalog/vehicle-ranking")
    assert result.status_code == 200
    assert result.json()["period"] is None
    assert result.json()["items"] == []

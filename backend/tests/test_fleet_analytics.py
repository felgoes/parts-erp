from datetime import UTC, datetime

from app.models import VehicleMarketRecord, VehicleMarketSnapshot
from app.services.fleet_analytics import fleet_overview, fleet_records


def _snapshot(db, snapshot_id: str, period: str) -> VehicleMarketSnapshot:
    snapshot = VehicleMarketSnapshot(
        id=snapshot_id,
        source="SENATRAN/RENAVAM",
        metric="fleet",
        period=period,
        source_url="https://example.test/fleet.zip",
        record_count=3,
        retrieved_at=datetime(2026, 10, 10, 12, tzinfo=UTC),
    )
    db.add(snapshot)
    return snapshot


def _record(
    snapshot_id: str,
    brand: str,
    model: str,
    year: int,
    value: int,
    *,
    category: str = "cars",
) -> None:
    return VehicleMarketRecord(
        id=f"{snapshot_id}-{brand}-{model}-{year}",
        snapshot_id=snapshot_id,
        record_key=f"key-{snapshot_id}-{brand}-{model}-{year}",
        nationality="França" if brand == "PEUGEOT" else "Brasil",
        brand=brand,
        model=model,
        vehicle_category=category,
        year_model=year,
        age_band="0 a 5 anos" if year >= 2021 else "6 a 10 anos",
        value=value,
        source_row_label=f"{brand}/{model}",
    )


def test_fleet_overview_comparison_and_interactive_filter_dimensions(db) -> None:
    _snapshot(db, "fleet-old", "2026-08")
    db.add(_record("fleet-old", "PEUGEOT", "208", 2022, 100))
    db.add(_record("fleet-old", "FIAT", "ARGO", 2020, 200))
    _snapshot(db, "fleet-new", "2026-09")
    db.add(_record("fleet-new", "PEUGEOT", "208", 2022, 120))
    db.add(_record("fleet-new", "PEUGEOT", "2008", 2020, 30))
    db.add(_record("fleet-new", "FIAT", "ARGO", 2020, 250))
    db.add(
        _record(
            "fleet-new",
            "YAMAHA",
            "FAZER",
            2022,
            80,
            category="motorcycles",
        )
    )
    db.commit()

    result = fleet_overview(db)
    assert result["period"] == "2026-09"
    assert result["total"] == 400
    assert result["change_pct"] == 33.33
    assert result["brands"][0] == {
        "label": "FIAT",
        "value": 250,
        "share_pct": 62.5,
    }
    assert result["filters"]["brands"] == ["FIAT", "PEUGEOT"]
    assert "YAMAHA" not in result["filters"]["brands"]

    peugeot = fleet_overview(db, brand="peugeot")
    assert peugeot["total"] == 150
    assert peugeot["brand_count"] == 1
    assert peugeot["model_count"] == 2

    motorcycles = fleet_overview(db, category="motorcycles")
    assert motorcycles["category"] == "motorcycles"
    assert motorcycles["total"] == 80
    assert motorcycles["brands"] == [
        {"label": "YAMAHA", "value": 80, "share_pct": 100.0}
    ]


def test_fleet_records_are_grouped_filtered_and_paginated(db) -> None:
    _snapshot(db, "fleet-directory", "2026-09")
    db.add(_record("fleet-directory", "PEUGEOT", "208", 2022, 120))
    db.add(_record("fleet-directory", "PEUGEOT", "208", 2023, 40))
    db.add(_record("fleet-directory", "FIAT", "ARGO", 2020, 250))
    db.add(
        _record(
            "fleet-directory",
            "HONDA",
            "CG 160 FAN",
            2022,
            90,
            category="motorcycles",
        )
    )
    db.commit()

    result = fleet_records(
        db,
        page=1,
        page_size=1,
        model="208",
        sort="fleet_desc",
    )
    assert result["total"] == 2
    assert result["items"][0]["value"] == 120
    assert result["items"][0]["share_pct"] == 75.0

import io
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import select

from app.models import (
    PushNotification,
    VehicleFleetImportRun,
    VehicleMarketRecord,
    VehicleMarketSnapshot,
)
from app.services import vehicle_fleet_import
from app.services.vehicle_fleet_parser import parse_fleet_zip, period_from_description
from app.services.vehicle_market_notifications import enqueue_vehicle_market_update


def _fleet_zip() -> bytes:
    output = io.BytesIO()
    content = (
        "UF;Município;Marca Modelo;Ano Fabricação Veículo CRV;Qtd. Veículos\r\n"
        "SÃO PAULO;SÃO PAULO;PEUGEOT/208 ACTIVE;2024; 3.0\r\n"
        "SÃO PAULO;CAMPINAS;PEUGEOT/208 ACTIVE;2024; 2.0\r\n"
        "SÃO PAULO;SANTOS;PEUGEOT/208 Active;2024; 1.0\r\n"
        "RIO DE JANEIRO;RIO DE JANEIRO;PEUGEOT/2008 ALLURE;2021; 4.0\r\n"
        "SÃO PAULO;SÃO PAULO;YAMAHA/FZ25 FAZER;2024; 7.0\r\n"
    ).encode()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("frota.txt", content)
    return output.getvalue()


def test_period_and_fleet_parser_aggregate_across_municipalities(tmp_path) -> None:
    path = tmp_path / "fleet.zip"
    path.write_bytes(_fleet_zip())
    parsed = parse_fleet_zip(path, "2026-09", full_validation=False)

    assert period_from_description("Frota de Setembro de 2026") == (
        "2026-09",
        "Setembro de 2026",
    )
    assert parsed.source_rows == 5
    assert parsed.total_vehicles == 17
    assert {(row.model, row.value) for row in parsed.aggregates} == {
        ("208 ACTIVE", 6),
        ("2008 ALLURE", 4),
        ("FZ25 FAZER", 7),
    }
    assert {row.category for row in parsed.aggregates} == {"cars", "motorcycles"}


def test_fleet_import_is_atomic_idempotent_and_enqueues_notification(
    db, tmp_path, monkeypatch
) -> None:
    resource_url = "https://official.example/fleet-september.zip"
    notifications = []
    monkeypatch.setattr(
        vehicle_fleet_import,
        "fleet_source_status",
        lambda: {
            "status": "available",
            "resource_url": resource_url,
            "period": "Frota de Setembro de 2026",
        },
    )
    monkeypatch.setattr(
        vehicle_fleet_import,
        "_download",
        lambda _url, destination: destination.write_bytes(_fleet_zip()),
    )
    monkeypatch.setattr(
        vehicle_fleet_import,
        "enqueue_vehicle_market_update",
        lambda _db, **kwargs: notifications.append(kwargs),
    )

    result = vehicle_fleet_import.import_latest_fleet(
        db, full_validation=False
    )
    repeated = vehicle_fleet_import.import_latest_fleet(
        db, full_validation=False
    )

    assert result["status"] == "completed"
    assert repeated["status"] == "completed"
    assert notifications == [{"period": "2026-09", "period_label": "Setembro de 2026"}]
    snapshot = db.scalar(
        select(VehicleMarketSnapshot).where(
            VehicleMarketSnapshot.source == "SENATRAN/RENAVAM",
            VehicleMarketSnapshot.metric == "fleet",
            VehicleMarketSnapshot.period == "2026-09",
        )
    )
    assert snapshot is not None
    assert snapshot.validation["total_vehicles"] == 17
    assert snapshot.validation["classification_version"] == 2
    records = db.scalars(
        select(VehicleMarketRecord).where(
            VehicleMarketRecord.snapshot_id == snapshot.id
        )
    ).all()
    assert sum(row.value for row in records) == 17
    assert {row.vehicle_category for row in records} == {"cars", "motorcycles"}
    assert db.scalar(select(VehicleFleetImportRun)).status == "completed"

    old_snapshot_id = snapshot.id
    snapshot.validation = {
        **snapshot.validation,
        "classification_version": 1,
    }
    db.commit()
    notifications.clear()
    refreshed = vehicle_fleet_import.import_latest_fleet(
        db, full_validation=False
    )
    refreshed_snapshot = db.scalar(
        select(VehicleMarketSnapshot).where(
            VehicleMarketSnapshot.source == "SENATRAN/RENAVAM",
            VehicleMarketSnapshot.metric == "fleet",
            VehicleMarketSnapshot.period == "2026-09",
        )
    )
    assert refreshed["status"] == "completed"
    assert refreshed_snapshot is not None and refreshed_snapshot.id != old_snapshot_id
    assert notifications == [{"period": "2026-09", "period_label": "Setembro de 2026"}]


def test_fleet_update_notification_is_deduplicated(db) -> None:
    first = enqueue_vehicle_market_update(
        db, period="2026-09", period_label="Setembro de 2026"
    )
    repeated = enqueue_vehicle_market_update(
        db, period="2026-09", period_label="Setembro de 2026"
    )

    assert first is not None
    assert repeated is not None and repeated.id == first.id
    assert first.category == "vehicle_market"
    assert first.data["route"] == "/fleet"
    assert len(db.scalars(select(PushNotification)).all()) == 1

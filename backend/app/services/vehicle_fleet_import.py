from __future__ import annotations

import hashlib
import tempfile
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import (
    VehicleFleetImportRun,
    VehicleMarketRecord,
    VehicleMarketSnapshot,
)
from app.services.vehicle_fleet_parser import (
    ParsedFleet,
    parse_fleet_zip,
    period_from_description,
)
from app.services.vehicle_market_fleet_source import fleet_source_status
from app.services.vehicle_market_notifications import enqueue_vehicle_market_update

SOURCE = "SENATRAN/RENAVAM"
MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024
_import_lock = threading.Lock()


def _record_key(
    snapshot_id: str, period: str, brand: str, model: str, year: int | None
) -> str:
    value = f"{snapshot_id}|{SOURCE}|fleet|{period}|{brand}|{model}|{year or ''}"
    return hashlib.sha256(value.casefold().encode()).hexdigest()


def _download(resource_url: str, destination: Path) -> None:
    received = 0
    try:
        with httpx.stream(
            "GET",
            resource_url,
            timeout=httpx.Timeout(60.0, read=180.0),
            follow_redirects=True,
        ) as response:
            response.raise_for_status()
            with destination.open("wb") as target:
                for chunk in response.iter_bytes(1024 * 1024):
                    received += len(chunk)
                    if received > MAX_DOWNLOAD_BYTES:
                        raise ValueError("O arquivo RENAVAM excedeu o limite de segurança.")
                    target.write(chunk)
    except httpx.HTTPError as exc:
        raise RuntimeError("Não foi possível baixar o arquivo oficial da frota.") from exc
    if received < 10 * 1024 * 1024:
        raise ValueError("O arquivo RENAVAM baixado é menor que o esperado.")


def _insert_aggregates(
    db: Session,
    *,
    snapshot_id: str,
    period: str,
    parsed: ParsedFleet,
) -> None:
    for start in range(0, len(parsed.aggregates), 5_000):
        rows = []
        for item in parsed.aggregates[start : start + 5_000]:
            rows.append(
                {
                    "id": str(uuid4()),
                    "snapshot_id": snapshot_id,
                    "record_key": _record_key(
                        snapshot_id, period, item.brand, item.model, item.year
                    ),
                    "nationality": item.nationality,
                    "brand": item.brand,
                    "model": item.model,
                    "vehicle_category": "veiculos",
                    "year_model": item.year,
                    "age_band": item.age_band,
                    "value": item.value,
                    "region": None,
                    "source_row_label": f"{item.brand}/{item.model}",
                }
            )
        db.bulk_insert_mappings(VehicleMarketRecord, rows)


def _run_import(
    db: Session,
    resource: dict[str, Any],
    run: VehicleFleetImportRun,
    *,
    full_validation: bool,
    archive_path: Path | None = None,
) -> None:
    period_info = period_from_description(resource.get("period"))
    if not period_info:
        raise ValueError("Não foi possível identificar a competência da frota publicada.")
    period, period_label = period_info
    if archive_path:
        parsed = parse_fleet_zip(archive_path, period, full_validation=full_validation)
    else:
        with tempfile.TemporaryDirectory(prefix="parts-erp-fleet-") as temporary:
            downloaded = Path(temporary) / "frota.zip"
            _download(str(resource["resource_url"]), downloaded)
            parsed = parse_fleet_zip(downloaded, period, full_validation=full_validation)
    snapshot_id = str(uuid4())
    _insert_aggregates(db, snapshot_id=snapshot_id, period=period, parsed=parsed)
    previous = db.scalar(
        select(VehicleMarketSnapshot).where(
            VehicleMarketSnapshot.source == SOURCE,
            VehicleMarketSnapshot.metric == "fleet",
            VehicleMarketSnapshot.period == period,
        )
    )
    if previous:
        db.execute(
            delete(VehicleMarketRecord).where(
                VehicleMarketRecord.snapshot_id == previous.id
            )
        )
        db.delete(previous)
        db.flush()
    db.add(
        VehicleMarketSnapshot(
            id=snapshot_id,
            source=SOURCE,
            metric="fleet",
            period=period,
            source_url=str(resource["resource_url"]),
            record_count=len(parsed.aggregates),
            published_at=None,
            validation={
                "resource_url": resource["resource_url"],
                "source_description": resource.get("period"),
                "source_rows": parsed.source_rows,
                "aggregate_count": len(parsed.aggregates),
                "total_vehicles": parsed.total_vehicles,
            },
        )
    )
    run.period = period
    run.status = "completed"
    run.source_rows = parsed.source_rows
    run.aggregate_count = len(parsed.aggregates)
    run.total_vehicles = parsed.total_vehicles
    run.completed_at = datetime.now(UTC)
    db.commit()
    try:
        enqueue_vehicle_market_update(db, period=period, period_label=period_label)
    except Exception:
        db.rollback()


def import_latest_fleet(
    db: Session,
    *,
    force: bool = False,
    full_validation: bool = True,
    archive_path: Path | None = None,
) -> dict[str, Any]:
    resource = fleet_source_status()
    if resource["status"] != "available" or not resource.get("resource_url"):
        return {"status": "unavailable", "message": "A publicação oficial está indisponível."}
    resource_url = str(resource["resource_url"])
    existing = db.scalar(
        select(VehicleFleetImportRun).where(
            VehicleFleetImportRun.resource_url == resource_url
        )
    )
    if existing and existing.status == "completed" and not force:
        return {
            "status": "completed",
            "period": existing.period,
            "run_id": existing.id,
            "message": "A publicação já foi importada.",
        }
    if not _import_lock.acquire(blocking=False):
        return {"status": "running", "message": "A frota já está sendo atualizada."}
    try:
        if existing is None:
            existing = VehicleFleetImportRun(
                id=str(uuid4()),
                resource_url=resource_url,
                period=period_from_description(resource.get("period"))[0]
                if period_from_description(resource.get("period"))
                else "0000-00",
                status="running",
            )
            db.add(existing)
        else:
            started_at = existing.started_at
            if started_at and started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=UTC)
            if (
                existing.status == "running"
                and started_at
                and started_at > datetime.now(UTC) - timedelta(hours=2)
            ):
                return {"status": "running", "run_id": existing.id}
            existing.status = "running"
            existing.error = None
            existing.started_at = datetime.now(UTC)
            existing.completed_at = None
        db.commit()
        db.refresh(existing)
        try:
            _run_import(
                db,
                resource,
                existing,
                full_validation=full_validation,
                archive_path=archive_path,
            )
        except Exception as exc:
            db.rollback()
            failed = db.get(VehicleFleetImportRun, existing.id)
            if failed:
                failed.status = "failed"
                failed.error = str(exc)[:500]
                failed.completed_at = datetime.now(UTC)
                db.commit()
            return {
                "status": "failed",
                "run_id": existing.id,
                "message": str(exc)[:500],
            }
        return {
            "status": "completed",
            "period": existing.period,
            "run_id": existing.id,
            "message": "Frota oficial importada e publicada.",
        }
    finally:
        _import_lock.release()


def import_latest_fleet_job() -> dict[str, Any]:
    with SessionLocal() as db:
        return import_latest_fleet(db)

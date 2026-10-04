from datetime import UTC, datetime
from time import perf_counter

import httpx
from sqlalchemy import text

from app.db.session import SessionLocal
from app.models import HealthSnapshot


def check_api() -> tuple[str, bool, float, str]:
    started = perf_counter()
    try:
        response = httpx.get("http://127.0.0.1:8000/health", timeout=5)
        return "API principal", response.is_success, (perf_counter() - started) * 1000, str(response.status_code)
    except httpx.HTTPError as exc:
        return "API principal", False, (perf_counter() - started) * 1000, type(exc).__name__


def check_database() -> tuple[str, bool, float, str]:
    started = perf_counter()
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return "Banco de dados", True, (perf_counter() - started) * 1000, "Conexão OK"
    except Exception as exc:
        return "Banco de dados", False, (perf_counter() - started) * 1000, type(exc).__name__


def check_public_catalog() -> tuple[str, bool, float, str]:
    started = perf_counter()
    try:
        response = httpx.get(
            "http://127.0.0.1:8080/api/v1/catalog/products",
            headers={"host": "www.goesautoparts.com.br"},
            timeout=5,
        )
        return "Catálogo público", response.is_success, (perf_counter() - started) * 1000, str(response.status_code)
    except httpx.HTTPError as exc:
        return "Catálogo público", False, (perf_counter() - started) * 1000, type(exc).__name__


def run() -> None:
    checked_at = datetime.now(UTC)
    results = [check_api(), check_database(), check_public_catalog()]
    with SessionLocal() as db:
        for result in results:
            db.add(
                HealthSnapshot(
                    check_name=result[0],
                    ok=result[1],
                    latency_ms=round(result[2], 2),
                    detail=result[3],
                    checked_at=checked_at,
                )
            )
        db.commit()


if __name__ == "__main__":
    run()

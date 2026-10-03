from datetime import UTC, datetime
from time import perf_counter

import httpx

from app.db.session import SessionLocal
from app.models import HealthSnapshot


def check_api() -> tuple[str, bool, float, str]:
    started = perf_counter()
    try:
        response = httpx.get("http://127.0.0.1:8000/health", timeout=5)
        return "api", response.is_success, (perf_counter() - started) * 1000, str(response.status_code)
    except httpx.HTTPError as exc:
        return "api", False, (perf_counter() - started) * 1000, type(exc).__name__


def run() -> None:
    checked_at = datetime.now(UTC)
    result = check_api()
    with SessionLocal() as db:
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

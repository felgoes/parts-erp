from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import get_settings

_cache: tuple[datetime, dict[str, Any]] | None = None


def fleet_source_status() -> dict[str, Any]:
    global _cache
    now = datetime.now(UTC)
    if _cache and _cache[0] > now.timestamp() - 21_600:
        return _cache[1]
    settings = get_settings()
    try:
        response = httpx.get(
            str(settings.senatran_fleet_package_url),
            timeout=15.0,
            follow_redirects=True,
        )
        response.raise_for_status()
        result = response.json().get("result", {})
        resources = [
            resource
            for resource in result.get("resources", [])
            if isinstance(resource, dict)
            and str(resource.get("format") or "").upper() == "ZIP"
        ]
        latest = max(resources, key=lambda resource: resource.get("created") or "")
        status = {
            "status": "available",
            "dataset_url": (
                "https://dados.transportes.gov.br/dataset/"
                "registro-nacional-de-veiculos-automotores-renavam"
            ),
            "resource_url": latest.get("url"),
            "period": latest.get("description"),
            "published_at": latest.get("created"),
            "format": latest.get("format"),
            "source": "SENATRAN/RENAVAM",
        }
    except (httpx.HTTPError, ValueError, TypeError):
        status = {
            "status": "unavailable",
            "dataset_url": (
                "https://dados.transportes.gov.br/dataset/"
                "registro-nacional-de-veiculos-automotores-renavam"
            ),
            "resource_url": None,
            "period": None,
            "published_at": None,
            "format": None,
            "source": "SENATRAN/RENAVAM",
        }
    _cache = (now.timestamp(), status)
    return status

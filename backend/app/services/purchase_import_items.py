from __future__ import annotations

import re
from typing import Any

from app.services.purchase_import_base import (
    MONEY,
    QUANTITY_HINT,
)
from app.services.purchase_import_danfe import (
    _extract_danfe_items,
    _extract_image_items,
    _extract_items_by_columns,
    _looks_like_danfe,
)
from app.services.purchase_import_profiles import (
    _normalize,
)
from app.services.purchase_import_reading import (
    _clean_text,
    _looks_like_column_label,
    _money,
)


def _extract_items(lines: list[str], profile_id: str | None = None) -> list[dict[str, Any]]:
    items = []
    if profile_id == "danfe" or _looks_like_danfe(lines):
        danfe_items = _extract_danfe_items(lines)
        if danfe_items:
            return danfe_items
    # AliExpress order details place the product/variant, unit price, and xN quantity
    # on separate lines. Require that complete local sequence to avoid summary totals.
    if profile_id == "aliexpress":
        for index in range(2, len(lines) - 1):
            price_match = re.fullmatch(rf"\s*({MONEY})\s*", lines[index], re.I)
            qty_match = re.fullmatch(r"\s*x\s*(\d+(?:[,.]\d+)?)\s*", lines[index + 1], re.I)
            if not price_match or not qty_match:
                continue
            unit = _money(price_match.group(1))
            qty = float(qty_match.group(1).replace(",", "."))
            description = " ".join(lines[index - 2 : index]).strip()
            if unit is None or qty <= 0 or not description:
                continue
            items.append(
                {
                    "description": description[:200],
                    "quantity": qty,
                    "unit_cost": unit,
                    "line_total": round(unit * qty, 2),
                    "confidence": 0.58,
                }
            )
        if items:
            return items[:100]
        return _extract_image_items(lines)
    # Deliberately conservative: only accept explicit quantity × price patterns.
    pattern = re.compile(
        rf"^(?P<description>.+?)\s+(?:x|×)\s*(?P<qty>\d+(?:[,.]\d+)?)\s+(?P<unit>{MONEY})(?:\s+(?P<total>{MONEY}))?\s*$",
        re.I,
    )
    for line in lines:
        match = pattern.match(line.strip())
        if not match:
            continue
        unit = _money(match.group("unit"))
        total = _money(match.group("total")) if match.group("total") else None
        qty = float(match.group("qty").replace(",", "."))
        if unit is None or qty <= 0:
            continue
        items.append(
            {
                "description": match.group("description").strip()[:200],
                "quantity": qty,
                "unit_cost": unit,
                "line_total": total if total is not None else round(qty * unit, 2),
                "confidence": 0.62,
            }
        )
    if items:
        return items[:100]
    # Grades em coluna (recibos de Alibaba, DANFE e afins): última tentativa, conservadora.
    return _extract_items_by_columns(lines)


def _item_candidates(lines: list[str]) -> list[dict[str, Any]]:
    """Quando nada é reconhecido, devolve linhas do texto que podem ser o item."""
    candidates: list[dict[str, Any]] = []
    for line in lines:
        value = line.strip()
        if len(value) < 8 or ":" in value or _looks_like_column_label(value):
            continue
        money = re.findall(r"(?:R\$|BRL|USD|US\$|\$)\s*\d[\d.,]*", value, re.I)
        numbers = re.findall(r"\b\d+(?:[.,]\d+)?\b", value)
        if not money and len(numbers) < 2:
            continue
        entry: dict[str, Any] = {"text": _clean_text(value)[:200]}
        if money:
            entry["unit_cost"] = _money(money[0])
        quantity = QUANTITY_HINT.search(_normalize(value))
        if quantity:
            entry["quantity"] = float(next(item for item in quantity.groups() if item))
        candidates.append(entry)
        if len(candidates) >= 8:
            break
    return candidates

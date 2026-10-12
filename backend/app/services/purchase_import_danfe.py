from __future__ import annotations

import re
from typing import Any

from app.services.purchase_import_base import (
    CELL_SPLIT,
    DANFE_VALUE_COLUMNS,
    NUMBER_CELL,
    QUANTITY_HINT,
)
from app.services.purchase_import_profiles import (
    _normalize,
)
from app.services.purchase_import_reading import (
    _clean_text,
    _looks_like_column_label,
    _money,
    _normalize_order_date,
)


def _extract_image_items(lines: list[str]) -> list[dict[str, Any]]:
    """Item de recibo fotografado: o OCR não preserva colunas, então usa o bloco do item."""
    start = next(
        (index for index, line in enumerate(lines) if "detalhes do item" in _normalize(line)),
        None,
    )
    if start is None:
        return []
    block = [line.strip() for line in lines[start + 1 : start + 8] if line.strip()]
    price_index = next(
        (index for index, line in enumerate(block) if re.search(r"(?:R\$|BRL)\s*\d", line, re.I)),
        None,
    )
    if price_index is None:
        return []
    price_match = re.search(r"(R\$\s*\d[\d.,]*|BRL\s*\d[\d.,]*)", block[price_index], re.I)
    unit_cost = _money(price_match.group(1)) if price_match else None
    if unit_cost is None or unit_cost <= 0:
        return []
    quantity = 1.0
    explicit = False
    for line in block[: price_index + 1]:
        hint = QUANTITY_HINT.search(_normalize(line))
        if hint:
            quantity = float(next(value for value in hint.groups() if value))
            explicit = True
            break
    description_parts = []
    for line in block[:price_index]:
        # Marcador de ícone/checkbox do recibo não é descrição.
        clean = re.sub(r"^[^\wÀ-ÿ]+", "", line).strip()
        if clean:
            description_parts.append(_clean_text(clean))
    description = " ".join(description_parts).strip()
    if len(description) < 3:
        return []
    return [
        {
            "description": description[:200],
            "quantity": quantity,
            "unit_cost": float(unit_cost),
            "line_total": round(unit_cost * quantity, 2),
            "confidence": 0.55,
            "source": "ocr",
            "quantity_derived": not explicit,
        }
    ]


def _split_cells(line: str) -> list[str]:
    return [cell.strip() for cell in CELL_SPLIT.split(line.strip()) if cell.strip()]


def _cell_number(cell: str) -> float | None:
    if not NUMBER_CELL.match(cell.strip()):
        return None
    return _money(cell)


def _extract_items_by_columns(lines: list[str]) -> list[dict[str, Any]]:
    """Lê linhas com colunas alinhadas: descrição, quantidade, unitário e total da linha."""
    items: list[dict[str, Any]] = []
    pending: list[str] = []
    for line in lines:
        value = line.strip()
        if not value:
            continue
        cells = _split_cells(value)
        numbers = [_cell_number(cell) for cell in cells]
        positions = [index for index, number in enumerate(numbers) if number is not None]
        if len(cells) < 3 or not positions or positions[0] == 0 or len(positions) < 2:
            # Linha de texto que pode ser a descrição (inclusive a segunda linha dela).
            if (
                ":" not in value
                and not _looks_like_column_label(value)
                and not NUMBER_CELL.match(value)
            ):
                pending.append(value)
            continue
        description_cells = cells[: positions[0]]
        values = [numbers[index] for index in positions]
        if len(values) >= 3:
            quantity, unit_cost, line_total = values[-3], values[-2], values[-1]
            derived = False
        else:
            unit_cost, line_total = values
            quantity = round(line_total / unit_cost, 3) if unit_cost else 0
            derived = True
        own_text = " ".join(description_cells).strip()
        # A descrição vem da própria linha; as linhas acima só completam quando a linha
        # é só de números.
        description = own_text if len(own_text) >= 3 else " ".join(pending[-2:]).strip()
        pending = []
        if (
            len(description) < 3
            or not quantity
            or quantity <= 0
            or unit_cost is None
            or unit_cost < 0
        ):
            continue
        items.append(
            {
                "description": _clean_text(description)[:200],
                "quantity": float(quantity),
                "unit_cost": float(unit_cost),
                "line_total": float(line_total),
                "confidence": 0.7,
                "source": "columns",
                "quantity_derived": derived,
            }
        )
    return items[:100]


def _looks_like_danfe(lines: list[str]) -> bool:
    text = _normalize("\n".join(lines[:160]))
    return ("vlr unit" in text and "valor total da nota" in text) or "documento auxiliar" in text


def _extract_danfe_fields(lines: list[str]) -> dict[str, dict[str, Any]]:
    """A DANFE escreve o rótulo em uma linha e o valor na linha de baixo, na mesma coluna."""
    fields: dict[str, dict[str, Any]] = {}
    joined = "\n".join(lines)
    key_match = re.search(r"(\d{4}(?:\s\d{4}){10}|\d{44})", joined)
    if key_match:
        fields["access_key"] = {
            "value": re.sub(r"\s", "", key_match.group(1)),
            "confidence": 0.9,
            "source": "documento",
        }
    issuer = re.search(r"RECEBEMOS DE (.+?) OS PRODUTOS", joined, re.I)
    if issuer:
        fields["supplier"] = {
            "value": _clean_text(issuer.group(1))[:160],
            "confidence": 0.85,
            "source": "documento",
        }
    series = re.search(r"S[EÉ]RIE:?\s*(\w+)", joined, re.I)
    if series:
        fields["document_series"] = {
            "value": series.group(1)[:20],
            "confidence": 0.85,
            "source": "documento",
        }
    document_number = re.search(r"N[ºo°]\s*([\d.]{3,20})", joined)
    if document_number:
        fields["document_number"] = {
            "value": document_number.group(1),
            "confidence": 0.85,
            "source": "documento",
        }
    issuer_cnpj = re.search(r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})", joined)
    if not issuer_cnpj:
        issuer_cnpj = re.search(r"CNPJ[:\s]*([\d./-]{14,20})", joined, re.I)
    if issuer_cnpj:
        fields["issuer_cnpj"] = {
            "value": issuer_cnpj.group(1),
            "confidence": 0.8,
            "source": "documento",
        }
    for index, line in enumerate(lines):
        cells = _split_cells(line)
        if not cells:
            continue
        normalized = [_normalize(cell) for cell in cells]
        next_cells = _split_cells(lines[index + 1]) if index + 1 < len(lines) else []
        if len(next_cells) != len(cells):
            continue
        for field, label in DANFE_VALUE_COLUMNS.items():
            if field in fields:
                continue
            target = _normalize(label)
            if target not in normalized:
                continue
            raw = next_cells[normalized.index(target)]
            value = _normalize_order_date(raw) if field == "date" else _money(raw)
            if value not in (None, ""):
                fields[field] = {"value": value, "confidence": 0.85, "source": "documento"}
    return fields


def _extract_danfe_items(lines: list[str]) -> list[dict[str, Any]]:
    """A grade da DANFE separa a descrição (duas linhas) das colunas numéricas."""
    items: list[dict[str, Any]] = []
    header = next(
        (
            index
            for index, line in enumerate(lines)
            if "vlr unit" in _normalize(line) and "qtd" in _normalize(line)
        ),
        None,
    )
    if header is None:
        return _extract_items_by_columns(lines)
    description_buffer: list[str] = []
    for index in range(header + 1, len(lines)):
        cells = _split_cells(lines[index])
        numeric_positions = [
            position for position, cell in enumerate(cells) if _cell_number(cell) is not None
        ]
        if not cells or len(numeric_positions) < 2:
            text = lines[index].strip()
            if cells and all(re.fullmatch(r"[A-Z]{2,10}", cell) for cell in cells):
                continue
            if text and not _looks_like_column_label(text) and ":" not in text:
                description_buffer.append(text)
            continue
        money_values = [
            _cell_number(cell)
            for cell in cells
            if _cell_number(cell) is not None and re.search(r"[.,]\d{2}$", cell)
        ]
        if len(money_values) < 2:
            continue
        code = cells[0] if numeric_positions[0] == 0 else ""
        unit = next((cell for cell in cells if re.fullmatch(r"[A-Za-z]{1,6}", cell)), "")
        unit_index = cells.index(unit) if unit else -1
        quantity = (
            _cell_number(cells[unit_index + 1])
            if unit_index >= 0 and unit_index + 1 < len(cells)
            else None
        )
        unit_cost, line_total = money_values[0], money_values[1]
        description = " ".join(description_buffer).strip()
        description_buffer = []
        # A DANFE continua a descrição na linha logo abaixo da linha de números.
        if index + 1 < len(lines):
            following = lines[index + 1].strip()
            if (
                following
                and not NUMBER_CELL.match(following)
                and not _looks_like_column_label(following)
                and ":" not in following
            ):
                description = f"{description} {following}".strip()
        if not description or quantity is None or quantity <= 0:
            continue
        items.append(
            {
                "description": _clean_text(description)[:200],
                "sku": code if code.isdigit() else "",
                "unit": unit.upper() if unit else "un",
                "quantity": float(quantity),
                "unit_cost": float(unit_cost),
                "line_total": float(line_total),
                "confidence": 0.72,
                "source": "columns",
                "quantity_derived": False,
            }
        )
    return items[:100]

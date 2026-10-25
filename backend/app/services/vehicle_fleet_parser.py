from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from app.services.vehicle_market import nationality_for_brand

EXPECTED_HEADER = {
    "UF",
    "Município",
    "Marca Modelo",
    "Ano Fabricação Veículo CRV",
    "Qtd. Veículos",
}
MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}
CANONICAL_BRANDS = {
    "GM": "Chevrolet",
    "CHEV": "Chevrolet",
    "VW": "Volkswagen",
    "M.BENZ": "Mercedes-Benz",
    "CITROEN": "Citroën",
}


@dataclass(frozen=True)
class FleetAggregate:
    brand: str
    model: str
    year: int | None
    age_band: str
    nationality: str
    value: int


@dataclass(frozen=True)
class ParsedFleet:
    aggregates: list[FleetAggregate]
    source_rows: int
    total_vehicles: int


def period_from_description(description: str | None) -> tuple[str, str] | None:
    match = re.search(r"\b([A-Za-zÀ-ÿ]+)\s+de\s+(\d{4})\b", description or "", re.I)
    if not match:
        return None
    month = MONTHS.get(match.group(1).casefold())
    if not month:
        return None
    year = int(match.group(2))
    month_name = match.group(1).strip()
    month_label = month_name[:1].upper() + month_name[1:].lower()
    return f"{year:04d}-{month:02d}", f"{month_label} de {year}"


def _age_band(year: int | None, period_year: int) -> str:
    if year is None or year <= 0:
        return "Não informado"
    age = max(0, period_year - year)
    if age <= 5:
        return "0 a 5 anos"
    if age <= 10:
        return "6 a 10 anos"
    if age <= 15:
        return "11 a 15 anos"
    if age <= 20:
        return "16 a 20 anos"
    return "21 anos ou mais"


def _quantity(value: str) -> int:
    raw = (value or "0").strip()
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        parsed = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("Quantidade de veículos inválida no arquivo RENAVAM.") from exc
    if parsed < 0:
        raise ValueError("Quantidade negativa no arquivo RENAVAM.")
    return int(parsed)


def _identity_key(value: str) -> str:
    return " ".join(value.split()).casefold()


def parse_fleet_zip(path: Path, period: str, *, full_validation: bool = True) -> ParsedFleet:
    totals: dict[tuple[str, str, int | None], int] = defaultdict(int)
    display_names: dict[tuple[str, str, int | None], tuple[str, str]] = {}
    source_rows = 0
    try:
        archive = ZipFile(path)
    except BadZipFile as exc:
        raise ValueError("O arquivo RENAVAM não é um ZIP válido.") from exc
    with archive:
        names = [
            name
            for name in archive.namelist()
            if name.lower().endswith((".txt", ".csv"))
        ]
        if len(names) != 1:
            raise ValueError("O ZIP RENAVAM deve conter exatamente um TXT ou CSV.")
        with archive.open(names[0]) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
            reader = csv.DictReader(text, delimiter=";")
            if set(reader.fieldnames or []) != EXPECTED_HEADER:
                raise ValueError("O arquivo RENAVAM tem colunas diferentes do esperado.")
            for row in reader:
                combined = (row.get("Marca Modelo") or "").strip()
                if "/" not in combined:
                    continue
                brand, model = (part.strip() for part in combined.split("/", 1))
                if not brand or not model:
                    continue
                brand = CANONICAL_BRANDS.get(brand.upper(), brand)
                year_text = (row.get("Ano Fabricação Veículo CRV") or "").strip()
                year = int(year_text) if year_text.isdigit() and int(year_text) > 0 else None
                key = (_identity_key(brand), _identity_key(model), year)
                display_names.setdefault(key, (brand, model))
                totals[key] += _quantity(row.get("Qtd. Veículos") or "")
                source_rows += 1
    period_year = int(period[:4])
    aggregates = []
    for key, value in totals.items():
        if value <= 0:
            continue
        brand, model = display_names[key]
        year = key[2]
        aggregates.append(
            FleetAggregate(
                brand=brand,
                model=model,
                year=year,
                age_band=_age_band(year, period_year),
                nationality=nationality_for_brand(brand) or "Não informada",
                value=value,
            )
        )
    total = sum(item.value for item in aggregates)
    if full_validation and (source_rows < 100_000 or len(aggregates) < 10_000):
        raise ValueError("O arquivo RENAVAM não atingiu o volume mínimo esperado.")
    if full_validation and not 10_000_000 <= total <= 500_000_000:
        raise ValueError("O total nacional da frota está fora da faixa de validação.")
    return ParsedFleet(
        aggregates=aggregates,
        source_rows=source_rows,
        total_vehicles=total,
    )

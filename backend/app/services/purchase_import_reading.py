from __future__ import annotations

import html
import re
from typing import Any

from app.services.purchase_import_base import (
    DATE_PATTERN,
    LABEL_ARTIFACT,
    MONEY,
)
from app.services.purchase_import_profiles import (
    _normalize,
)


def _money(value: str) -> float | None:
    raw = re.sub(r"R\$|BRL|USD|US\$|\$", "", value, flags=re.IGNORECASE).replace(" ", "")
    if "," in raw and "." in raw:
        decimal_mark = "," if raw.rfind(",") > raw.rfind(".") else "."
        grouping_mark = "." if decimal_mark == "," else ","
        raw = raw.replace(grouping_mark, "").replace(decimal_mark, ".")
    elif "," in raw:
        raw = (
            raw.replace(".", "").replace(",", ".")
            if re.search(r",\d{1,2}$", raw)
            else raw.replace(",", "")
        )
    try:
        number = float(raw)
        return round(number, 2) if number == number and abs(number) < 1e12 else None
    except ValueError:
        return None


def _money_entry(value_part: str) -> tuple[float, str | None] | None:
    match = re.match(rf"\s*({MONEY})\s*(?:\(([A-Za-z\$]{{2,9}})\))?", value_part, re.I)
    if not match:
        return None
    amount = _money(match.group(1))
    if amount is None:
        return None
    currency = _currency_of(match.group(1)) or _currency_of(match.group(2) or "")
    return amount, currency


def _currency_of(text: str) -> str | None:
    upper = text.upper()
    if re.search(r"R\$|\bBRL\b", upper):
        return "BRL"
    if re.search(r"US\$|\bUSD\b", upper):
        return "USD"
    if re.search(r"\bEUR\b|€", upper):
        return "EUR"
    if "$" in upper:
        return "USD"
    return None


def _document_currency(fields: dict[str, dict[str, Any]]) -> str | None:
    for field in ("total", "paid", "subtotal", "shipping", "discount", "tax"):
        currency = (fields.get(field) or {}).get("currency")
        if currency:
            return currency
    return None


def _exchange_rate(text: str) -> dict[str, Any] | None:
    match = re.search(r"1\s*([A-Za-z]{3})\s*=\s*([\d.,]+)\s*([A-Za-z]{3})", text)
    if not match:
        return None
    raw = match.group(2).replace(" ", "")
    if "," in raw and "." in raw:
        decimal_mark = "," if raw.rfind(",") > raw.rfind(".") else "."
        raw = raw.replace("." if decimal_mark == "," else ",", "").replace(decimal_mark, ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        rate = float(raw)
    except ValueError:
        return None
    if not rate or rate <= 0 or rate >= 1_000_000:
        return None
    return {
        "rate": rate,
        "from_currency": match.group(1).upper(),
        "to_currency": match.group(3).upper(),
    }


def _paid_details(text: str) -> tuple[str | None, str | None]:
    with_method = re.search(r"p(?:aid|ago)\s+(?:on|em)\s+([^()\n]+?)\s*\(([^)\n]+)\)", text, re.I)
    if with_method:
        return _normalize_order_date(with_method.group(1)), _clean_text(with_method.group(2))[:40]
    plain = re.search(r"p(?:aid|ago)\s+(?:on|em)\s+([^\n]+)", text, re.I)
    if plain:
        return _normalize_order_date(plain.group(1)), None
    return None, None


def _normalize_order_date(value: str) -> str | None:
    months = {
        "jan": 1,
        "january": 1,
        "fev": 2,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "abr": 4,
        "apr": 4,
        "april": 4,
        "mai": 5,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "ago": 8,
        "aug": 8,
        "august": 8,
        "set": 9,
        "sep": 9,
        "sept": 9,
        "september": 9,
        "out": 10,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dez": 12,
        "dec": 12,
        "december": 12,
        "janeiro": 1,
        "fevereiro": 2,
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
    text = _normalize(value).replace(",", " ").replace(" de ", " ")
    text = re.sub(r"\b(\d{1,2})(st|nd|rd|th)\b", r"\1", text)
    text = re.sub(r"\([a-z]{2,5}\)", " ", text)
    text = " ".join(text.split())
    iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if iso:
        return text
    numeric = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", text)
    if numeric:
        day, month, year = map(int, numeric.groups())
    else:
        month_first = re.fullmatch(r"([a-z]+)\s+(\d{1,2})\s+(\d{4})", text)
        day_first = re.fullmatch(r"(\d{1,2})\s+([a-z]+)\s+(\d{4})", text)
        if month_first and month_first.group(1) in months:
            month, day, year = (
                months[month_first.group(1)],
                int(month_first.group(2)),
                int(month_first.group(3)),
            )
        elif day_first and day_first.group(2) in months:
            day, month, year = (
                int(day_first.group(1)),
                months[day_first.group(2)],
                int(day_first.group(3)),
            )
        else:
            return None
    if year < 100:
        year += 2000 if year < 70 else 1900
    try:
        from datetime import date

        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _looks_like_column_label(value: str) -> bool:
    """Evita gravar o rótulo da coluna vizinha como se fosse o dado do campo."""
    normalized = _normalize(value)
    return any(artifact in normalized for artifact in LABEL_ARTIFACT)


def _clean_text(value: str) -> str:
    return html.unescape(value).strip()


def _extract_labeled(lines: list[str], labels: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
    """Casa cada linha com o rótulo mais específico e preenche cada campo uma única vez.

    P5: "taxa de pagamento" também começa com "taxa" (rótulo genérico de imposto). A escolha
    do rótulo mais longo que casa com a linha garante que a taxa de pagamento entre como taxa
    extra, e o mesmo valor nunca é gravado em dois campos.
    """
    output: dict[str, dict[str, Any]] = {}
    money_fields = {"total", "subtotal", "shipping", "discount", "tax", "extras", "paid"}
    candidates: dict[str, list[dict[str, Any]]] = {}

    # 1. Qual rótulo vence cada linha: o mais longo (mais específico) que casa no início dela.
    winners: dict[int, tuple[str, str, str]] = {}
    for field, variants in labels.items():
        for i, line in enumerate(lines):
            normalized_line = _normalize(line)
            matched = next(
                (
                    label
                    for label in sorted((_normalize(x) for x in variants), key=len, reverse=True)
                    if re.match(rf"^{re.escape(label)}(?:\b|\s|:|#|-)", normalized_line)
                ),
                None,
            )
            if not matched:
                continue
            current = winners.get(i)
            if current is None or len(matched) > len(current[1]):
                winners[i] = (field, matched, normalized_line)

    # 2. Com o dono de cada linha definido, extrai o valor do jeito que cada campo pede.
    for i in sorted(winners):
        field, matched, normalized_line = winners[i]
        variants = labels.get(field, [])
        value_part = normalized_line[len(matched) :].strip(" :#-\t")
        if not value_part and i + 1 < len(lines):
            value_part = _normalize(lines[i + 1])
        if not value_part:
            continue
        if field in money_fields:
            entry = _money_entry(value_part)
            if entry is None and field == "paid" and i:
                entry = _money_entry(_normalize(lines[i - 1]))
            if entry is None:
                continue
            candidates.setdefault(field, []).append(
                {
                    "value": entry[0],
                    "currency": entry[1],
                    "confidence": 0.78,
                    "source": "label",
                }
            )
            continue
        if field in output:
            continue
        if field == "date":
            date_match = re.search(DATE_PATTERN, value_part)
            value = _normalize_order_date(date_match.group(1)) if date_match else None
        else:
            raw_variant = next(
                (original for original in variants if _normalize(original) == matched),
                None,
            )
            raw_remainder = lines[i]
            if raw_variant:
                raw_match = re.match(rf"\s*{re.escape(raw_variant)}\s*[:\-#]?\s*", lines[i], re.I)
                if raw_match:
                    raw_remainder = lines[i][raw_match.end() :]
            # A segunda coluna do recibo vem depois de um vão largo: corta ali.
            value = _clean_text(re.split(r"\s{3,}", raw_remainder)[0].strip(" :#-\t"))[:160]
            if _looks_like_column_label(value):
                continue
        if value not in (None, ""):
            output[field] = {"value": value, "confidence": 0.78, "source": "label"}
    for field, found in candidates.items():
        # O recibo da Alibaba traz o total em BRL e a mesma quantia em USD: a linha em reais vence.
        best = next((entry for entry in found if entry.get("currency") == "BRL"), found[0])
        if best.get("currency") is None:
            best.pop("currency", None)
        output[field] = best
    return output

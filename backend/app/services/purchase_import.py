from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.services import (
    purchase_import_base,  # noqa: F401  (reexportado)
    purchase_import_danfe,  # noqa: F401  (reexportado)
    purchase_import_items,  # noqa: F401  (reexportado)
    purchase_import_ocr,  # noqa: F401  (reexportado)
    purchase_import_profiles,  # noqa: F401  (reexportado)
    purchase_import_reading,  # noqa: F401  (reexportado)
)
from app.services.nfe_xml import parse_nfe_xml
from app.services.purchase_import_base import (  # noqa: F401  (reexportado)
    _OCR_SLOT,
    CELL_SPLIT,
    DANFE_VALUE_COLUMNS,
    DATE_PATTERN,
    FIELD_LABELS,
    LABEL_ARTIFACT,
    MARKETPLACES,
    MAX_BYTES,
    MAX_PDF_PAGES,
    MONEY,
    NUMBER_CELL,
    PROFILE_SCHEMA,
    QUANTITY_HINT,
)
from app.services.purchase_import_danfe import (  # noqa: F401  (reexportado)
    _cell_number,
    _extract_danfe_fields,
    _extract_danfe_items,
    _extract_image_items,
    _extract_items_by_columns,
    _looks_like_danfe,
    _split_cells,
)
from app.services.purchase_import_items import (  # noqa: F401  (reexportado)
    _extract_items,
    _item_candidates,
)
from app.services.purchase_import_ocr import (  # noqa: F401  (reexportado)
    _extract_text,
    _ocr_image_or_pdf,
)
from app.services.purchase_import_profiles import (  # noqa: F401  (reexportado)
    _custom_profiles,
    _normalize,
    _profile_dir,
    _profile_from_filename,
    _profile_labels,
    delete_profile,
    detect_profile,
    list_profiles,
    save_profile,
    validate_profile,
)
from app.services.purchase_import_reading import (  # noqa: F401  (reexportado)
    _clean_text,
    _currency_of,
    _document_currency,
    _exchange_rate,
    _extract_labeled,
    _looks_like_column_label,
    _money,
    _money_entry,
    _normalize_order_date,
    _paid_details,
)


async def analyze_upload(upload: UploadFile, selected_profile: str | None = None) -> dict[str, Any]:
    if selected_profile is not None:
        known_profiles = {profile["profile_id"] for profile in list_profiles()}
        if selected_profile not in known_profiles:
            raise ValueError("O perfil selecionado não existe.")
    filename = Path(upload.filename or "").name
    content = await upload.read(MAX_BYTES + 1)
    if not content or len(content) > MAX_BYTES:
        raise ValueError("O documento deve ter conteúdo e até 15 MB.")
    if filename.lower().endswith(".xml"):
        parsed = parse_nfe_xml(content)
        total_field = parsed["fields"].get("total") or {}
        shipping_field = parsed["fields"].get("shipping") or {}
        tax_field = parsed["fields"].get("tax") or {}
        discount_field = parsed["fields"].get("discount") or {}
        items_total = (
            round(sum(item["line_total"] for item in parsed["items"]), 2)
            if parsed["items"]
            else None
        )
        total_value = total_field.get("value")
        closing = None
        if total_value is not None and items_total is not None:
            closing = round(
                items_total
                + (shipping_field.get("value") or 0)
                + (tax_field.get("value") or 0)
                - (discount_field.get("value") or 0)
                - total_value,
                2,
            )
        return {
            "filename": filename,
            "profile": {
                "profile_id": "nfe_xml",
                "name": "NF-e XML",
                "confidence": 1.0,
                "selected": True,
            },
            "fields": parsed["fields"],
            "items": parsed["items"],
            "warnings": parsed["warnings"],
            "currency": "BRL",
            "exchange_rate": None,
            "exchange_rate_from": None,
            "exchange_rate_to": None,
            "paid": None,
            "check": {
                "items_total": items_total,
                "subtotal": (parsed["fields"].get("subtotal") or {}).get("value"),
                "subtotal_difference": None,
                "shipping": shipping_field.get("value"),
                "tax": tax_field.get("value"),
                "discount": discount_field.get("value"),
                "total": total_value,
                "closing_difference": closing,
                "balanced": closing is not None and abs(closing) <= 0.05,
            },
            "text": None,
            "candidates": [],
        }
    if filename.lower().endswith(".pdf") and not content.startswith(b"%PDF-"):
        raise ValueError("O arquivo não contém um PDF válido.")
    if filename.lower().endswith((".jpg", ".jpeg")) and not content.startswith(b"\xff\xd8\xff"):
        raise ValueError("O arquivo não contém uma imagem JPEG válida.")
    if filename.lower().endswith(".png") and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("O arquivo não contém uma imagem PNG válida.")
    if not _OCR_SLOT.acquire(blocking=False):
        raise RuntimeError("Outro documento está sendo analisado. Tente novamente em instantes.")
    try:
        text, source = await asyncio.to_thread(_extract_text, filename, content)
    finally:
        _OCR_SLOT.release()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    ocr_quality = 1.0
    quality_line = next((line for line in lines if line.startswith("OCR_QUALITY_SIGNAL=")), None)
    if quality_line:
        try:
            ocr_quality = max(0.0, min(1.0, float(quality_line.split("=", 1)[1]) / 100))
            lines.remove(quality_line)
        except ValueError:
            pass
    profile = detect_profile(text, selected_profile, filename)
    labels = _profile_labels(profile["profile_id"])
    fields = _extract_labeled(lines, labels)
    if _looks_like_danfe(lines):
        for field, entry in _extract_danfe_fields(lines).items():
            fields.setdefault(field, entry)
    for field in fields.values():
        field["confidence"] = round(field["confidence"] * ocr_quality, 2)
        field["source"] = source
    items = _extract_items(lines, profile["profile_id"])
    for item in items:
        item["confidence"] = round(item["confidence"] * ocr_quality, 2)
    warnings = []
    if not profile["profile_id"]:
        warnings.append(
            "Marketplace não identificado com segurança. Selecione o perfil ou confira os campos."
        )
    if not items:
        warnings.append(
            "Nenhum item foi identificado com confiança suficiente; adicione ou corrija as linhas."
        )
    items_total = round(sum(item["line_total"] for item in items), 2) if items else None
    shipping = (fields.get("shipping") or {}).get("value")
    tax = (fields.get("tax") or {}).get("value")
    discount = (fields.get("discount") or {}).get("value")
    total = (fields.get("total") or {}).get("value")
    subtotal = (fields.get("subtotal") or {}).get("value")
    closing_difference = None
    if total is not None and items_total is not None:
        closing_difference = round(
            items_total + (shipping or 0) + (tax or 0) - (discount or 0) - total, 2
        )
    subtotal_difference = None
    if subtotal is not None and items_total is not None:
        subtotal_difference = round(items_total - subtotal, 2)
    if total is None:
        warnings.append("Total não identificado; confira o documento antes de continuar.")
    elif closing_difference is not None and abs(closing_difference) > 0.05:
        warnings.append(
            "A conferência não fecha: itens + frete + impostos − descontos difere do total do "
            f"documento em R$ {abs(closing_difference):.2f}."
        )
    if subtotal_difference is not None and abs(subtotal_difference) > 0.05:
        warnings.append(
            "A soma dos itens difere do subtotal do documento em "
            f"R$ {abs(subtotal_difference):.2f}."
        )
    currency = _document_currency(fields)
    rate = _exchange_rate(text)
    paid_date, paid_method = _paid_details(text)
    paid = fields.get("paid")
    return {
        "filename": filename,
        "source": source,
        "profile": profile,
        "fields": fields,
        "items": items,
        "warnings": warnings,
        "currency": currency,
        "exchange_rate": rate["rate"] if rate else None,
        "exchange_rate_from": rate["from_currency"] if rate else None,
        "exchange_rate_to": rate["to_currency"] if rate else None,
        "paid": {
            "amount": paid["value"],
            "currency": paid.get("currency") or currency,
            "date": paid_date,
            "method": paid_method,
        }
        if paid
        else None,
        "check": {
            "items_total": items_total,
            "subtotal": subtotal,
            "subtotal_difference": subtotal_difference,
            "shipping": shipping,
            "tax": tax,
            "discount": discount,
            "total": total,
            "closing_difference": closing_difference,
            "balanced": (
                closing_difference is not None
                and abs(closing_difference) <= 0.05
                and (subtotal_difference is None or abs(subtotal_difference) <= 0.05)
            ),
        },
        "text": text,
        "candidates": _item_candidates(lines) if not items else [],
    }

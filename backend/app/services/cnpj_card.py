from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from app.services.purchase_import_ocr import _extract_text, _ocr_image_or_pdf

MAX_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 5
MAX_IMAGE_PIXELS = 30_000_000


def validate_cnpj(value: str | None) -> bool:
    digits = "".join(character for character in (value or "") if character.isdigit())
    if len(digits) != 14 or digits == digits[0] * 14:
        return False
    for size in (12, 13):
        weights = list(range(size - 7, 1, -1)) + list(range(9, 1, -1))
        total = sum(
            int(digit) * weight
            for digit, weight in zip(digits[:size], weights, strict=True)
        )
        check = 11 - total % 11
        if int(digits[size]) != (0 if check >= 10 else check):
            return False
    return True


def _assert_signature(filename: str, content: bytes) -> str:
    extension = Path(filename).suffix.lower()
    signatures = {
        ".pdf": content.startswith(b"%PDF-"),
        ".jpg": content.startswith(b"\xff\xd8\xff"),
        ".jpeg": content.startswith(b"\xff\xd8\xff"),
        ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
    }
    if extension not in signatures:
        raise ValueError("Envie o Cartão CNPJ em PDF, JPG ou PNG.")
    if not signatures[extension]:
        raise ValueError("O conteúdo do arquivo não corresponde ao formato informado.")
    return extension


def _pdf_pages(path: Path) -> int:
    pdfinfo = shutil.which("pdfinfo")
    if not pdfinfo:
        raise RuntimeError("Leitura de PDF indisponível no servidor.")
    result = subprocess.run(  # noqa: S603
        [pdfinfo, str(path)], capture_output=True, text=True, timeout=15, check=True
    )
    match = re.search(r"^Pages:\s+(\d+)", result.stdout, re.MULTILINE)
    if not match:
        raise ValueError("Não foi possível validar o PDF enviado.")
    pages = int(match.group(1))
    if pages < 1 or pages > MAX_PDF_PAGES:
        raise ValueError(f"O PDF deve ter até {MAX_PDF_PAGES} páginas.")
    return pages


def _read_text(filename: str, content: bytes) -> tuple[str, str]:
    extension = _assert_signature(filename, content)
    with tempfile.TemporaryDirectory(prefix="cnpj-card-") as temporary:
        folder = Path(temporary)
        path = folder / f"card{extension}"
        path.write_bytes(content)
        if extension == ".pdf":
            _pdf_pages(path)
            text, source = _extract_text(filename, content)
            if source == "pdf_text" and len(re.sub(r"\s+", "", text)) < 120:
                text, source = _ocr_image_or_pdf(path, pdf=True), "ocr"
            return text, source
        return _ocr_image_or_pdf(content), "ocr"


def _clean(value: str | None, limit: int = 300) -> str | None:
    if value is None:
        return None
    result = " ".join(value.replace("\x00", " ").split()).strip(" :;|-")
    return result[:limit] or None


def _label_value(text: str, label: str, stop: str = r"\n") -> str | None:
    pattern = rf"(?im)^\s*{label}\s*:?\s*(.*?)(?={stop}|$)"
    match = re.search(pattern, text)
    return _clean(match.group(1)) if match else None


def _date_value(value: str | None) -> str | None:
    match = re.search(r"(\d{2})[/-](\d{2})[/-](\d{4})", value or "")
    if not match:
        return None
    day, month, year = map(int, match.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _explicit_bool(text: str, label: str) -> bool | None:
    match = re.search(rf"(?im)^\s*{label}\s*:?\s*(SIM|NAO|NÃO)\b", text)
    if not match:
        return None
    return match.group(1).casefold() == "sim"


def _extract_fields(text: str, source: str, quality: float | None) -> dict[str, Any]:
    flat_text = " ".join(text.split())
    cnpj_match = re.search(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b", flat_text)
    cnpj = (
        "".join(character for character in cnpj_match.group(0) if character.isdigit())
        if cnpj_match
        else None
    )
    cnae_matches = re.findall(r"\b(\d{2}\.\d{2}-\d/\d{2})\s*[-–]?\s*([^;\n]{0,180})", text)
    postal_match = re.search(r"\b\d{5}-?\d{3}\b", flat_text)
    street = _label_value(text, r"LOGRADOURO")
    number = _label_value(text, r"N[ÚU]MERO")
    district = _label_value(text, r"BAIRRO(?:/DISTRITO)?")
    city = _label_value(text, r"MUNIC[ÍI]PIO")
    state = _label_value(text, r"UF")
    phone_match = re.search(r"(?im)^\s*TELEFONE\s*:?\s*([+()\d\s.-]{8,})", text)
    email_match = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.I)
    values = {
        "identification.cnpj": cnpj,
        "identification.legal_name": _label_value(text, r"NOME EMPRESARIAL"),
        "identification.trade_name": _label_value(text, r"NOME DE FANTASIA"),
        "identification.branch": (
            "filial"
            if re.search(r"(?i)\bFILIAL\b", text)
            else "matriz"
            if re.search(r"(?i)\bMATRIZ\b", text)
            else None
        ),
        "identification.registration_status": _label_value(text, r"SITUA[ÇC][ÃA]O CADASTRAL"),
        "identification.status_date": _date_value(
            _label_value(text, r"DATA DA SITUA[ÇC][ÃA]O CADASTRAL")
        ),
        "identification.status_reason": _label_value(
            text, r"MOTIVO DA SITUA[ÇC][ÃA]O CADASTRAL"
        ),
        "identification.opened_on": _date_value(_label_value(text, r"DATA DE ABERTURA")),
        "identification.legal_nature_code": (
            re.search(r"(?im)^\s*NATUREZA JUR[ÍI]DICA\s*:?\s*(\d{3,4}-\d)", text).group(1)
            if re.search(r"(?im)^\s*NATUREZA JUR[ÍI]DICA\s*:?\s*(\d{3,4}-\d)", text)
            else None
        ),
        "identification.legal_nature_description": re.sub(
            r"^\s*\d{3,4}-\d\s*[-–]?\s*",
            "",
            _label_value(text, r"NATUREZA JUR[ÍI]DICA") or "",
        )
        or None,
        "identification.company_size": _label_value(text, r"PORTE"),
        "identification.simples_opt_in": _explicit_bool(
            text, r"OP[ÇC][ÃA]O PELO SIMPLES NACIONAL"
        ),
        "identification.mei_opt_in": _explicit_bool(text, r"OP[ÇC][ÃA]O PELO MEI"),
        "activities.primary_cnae_code": cnae_matches[0][0] if cnae_matches else None,
        "activities.primary_cnae_description": _clean(cnae_matches[0][1])
        if cnae_matches
        else None,
        "activities.secondary_cnaes": [code for code, _ in cnae_matches[1:]],
        "addresses.fiscal.postal_code": postal_match.group(0) if postal_match else None,
        "addresses.fiscal.street": street,
        "addresses.fiscal.number": number,
        "addresses.fiscal.district": district,
        "addresses.fiscal.city": city,
        "addresses.fiscal.state": state[-2:] if state else None,
        "contact.phone": _clean(phone_match.group(1)) if phone_match else None,
        "contact.business_email": email_match.group(0).lower() if email_match else None,
    }
    output: dict[str, Any] = {}
    low = quality is not None and quality < 65
    for key, value in values.items():
        if value not in (None, "", []):
            confidence = "low" if low else "medium" if source == "ocr" else "high"
            output[key] = {"value": value, "confidence": confidence, "origin": "cnpj_card"}
    return output


def _read_current(profile: dict[str, Any], path: str) -> Any:
    value: Any = profile
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _same(left: Any, right: Any) -> bool:
    if left in (None, "") and right in (None, ""):
        return True
    return str(left).strip().casefold() == str(right).strip().casefold()


def parse_card(
    filename: str,
    content: bytes,
    *,
    current_data: dict[str, Any],
    manual_fields: list[str],
) -> dict[str, Any]:
    if not content or len(content) > MAX_BYTES:
        raise ValueError("O Cartão CNPJ deve ter conteúdo e no máximo 10 MB.")
    text, source = _read_text(filename, content)
    quality_match = re.search(r"OCR_QUALITY_SIGNAL=([\d.]+)", text)
    quality = float(quality_match.group(1)) if quality_match else None
    fields = _extract_fields(text, source, quality)
    cnpj = (fields.get("identification.cnpj") or {}).get("value")
    if not cnpj or not validate_cnpj(cnpj):
        raise ValueError(
            "O Cartão CNPJ não contém um CNPJ válido. Confira o documento ou preencha manualmente."
        )
    status = str((fields.get("identification.registration_status") or {}).get("value") or "")
    warning = (
        "A situação cadastral não está ativa; a aplicação exige uma decisão explícita."
        if status and status.casefold() not in {"ativa", "ativo"}
        else None
    )
    expected = {
        "identification.cnpj",
        "identification.legal_name",
        "identification.registration_status",
        "addresses.fiscal.postal_code",
        "addresses.fiscal.street",
        "addresses.fiscal.city",
        "addresses.fiscal.state",
        "activities.primary_cnae_code",
    }
    missing = sorted(expected - set(fields))
    low = sorted(
        path for path, field in fields.items() if field["confidence"] in {"low", "medium"}
    )
    differences = []
    for path, field in fields.items():
        current = _read_current(current_data, path)
        if current is not None and not _same(field["value"], current):
            differences.append({"field": path, "current": current, "extracted": field["value"]})
    return {
        "document": {
            "sha256": hashlib.sha256(content).hexdigest(),
            "content_type": Path(filename).suffix.lower().lstrip("."),
            "reading": source,
            "ocr_quality": quality,
            "retained": False,
        },
        "fields": fields,
        "missing": missing,
        "low_confidence": low,
        "differences": differences,
        "protected_manual_fields": sorted(set(manual_fields) & set(fields)),
        "cnpj_valid": True,
        "status_warning": warning,
        "lookup_available": False,
        "lookup_message": "Consulta oficial do CNPJ não está configurada.",
    }

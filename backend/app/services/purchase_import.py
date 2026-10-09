from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

PROFILE_SCHEMA = "parts-erp-purchase-import-profile/v1"
MAX_BYTES = 15 * 1024 * 1024
MAX_PDF_PAGES = 10
MARKETPLACES: dict[str, dict[str, Any]] = {
    "aliexpress": {
        "name": "AliExpress",
        "terms": ["aliexpress"],
        "field_labels": {
            "total": ["order total", "total paid", "total do pedido", "valor total"],
            "shipping": ["shipping fee", "frete", "delivery fee"],
            "discount": ["coupon", "discount", "desconto"],
        },
    },
    "mercado_livre": {
        "name": "Mercado Livre",
        "terms": ["mercado livre", "mercadolivre", "meli", "mercadolibre"],
        "field_labels": {
            "supplier": ["vendedor", "loja", "seller"],
            "order_number": ["número da compra", "número do pedido", "pedido nº"],
            "total": ["total da compra", "total pago", "valor total"],
        },
    },
    "shopee": {
        "name": "Shopee",
        "terms": ["shopee", "spaylater", "pedido shopee"],
        "field_labels": {
            "supplier": ["loja", "seller"],
            "order_number": ["id do pedido", "order id"],
            "total": ["total do pedido", "total pago", "valor total"],
            "shipping": ["taxa de envio", "frete"],
            "discount": ["desconto da loja", "cupom"],
        },
    },
    "amazon": {
        "name": "Amazon",
        "terms": ["amazon", "amazon.com.br"],
        "field_labels": {
            "supplier": ["sold by", "vendido por"],
            "order_number": ["order number", "número do pedido"],
            "total": ["order total", "total do pedido"],
            "shipping": ["shipping & handling", "frete e manuseio"],
        },
    },
    "alibaba": {
        "name": "Alibaba",
        "terms": ["alibaba.com", "trade assurance", "alibaba group"],
        "field_labels": {
            "supplier": ["supplier", "seller"],
            "order_number": ["order number", "trade order"],
            "total": ["total amount", "order total"],
            "shipping": ["shipping cost", "freight"],
        },
    },
}
FIELD_LABELS: dict[str, list[str]] = {
    "supplier": ["seller", "sold by", "fornecedor", "vendido por", "loja"],
    "order_number": ["order number", "order id", "número do pedido", "pedido nº", "pedido no"],
    "date": ["order date", "purchase date", "data do pedido", "data da compra"],
    "subtotal": ["subtotal", "item subtotal", "subtotal dos produtos"],
    "shipping": ["shipping", "frete", "delivery fee"],
    "discount": ["discount", "desconto", "coupon"],
    "total": ["order total", "total do pedido", "total pago", "valor total", "total"],
    "tax": ["tax", "taxes", "taxa", "imposto", "impostos", "vat", "iva"],
}
MONEY = r"(?:R\$\s*)?-?\s*(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{2}|\.\d{2})"
_OCR_SLOT = threading.BoundedSemaphore(1)


def _normalize(value: str) -> str:
    return " ".join(
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower().split()
    )


def _profile_dir() -> Path:
    from app.core.config import get_settings

    path = Path(get_settings().documents_dir).resolve() / "purchase-import-profiles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_profiles() -> list[dict[str, Any]]:
    profiles = [
        {"profile_id": key, "name": value["name"], "kind": "built_in", "version": 1}
        for key, value in MARKETPLACES.items()
    ]
    for path in sorted(_profile_dir().glob("*.json")):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            profiles.append(
                {
                    "profile_id": obj["profile_id"],
                    "name": obj["name"],
                    "kind": "custom",
                    "version": obj["version"],
                }
            )
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return profiles


def validate_profile(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict) or obj.get("schema") != PROFILE_SCHEMA:
        raise ValueError(f"Use um perfil com schema {PROFILE_SCHEMA}.")
    allowed = {"schema", "profile_id", "name", "version", "match_terms", "field_labels"}
    if set(obj) - allowed:
        raise ValueError("O perfil contém propriedades não permitidas.")
    pid, name = obj.get("profile_id"), obj.get("name")
    if not isinstance(pid, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,49}", pid):
        raise ValueError("profile_id deve conter 2 a 50 letras minúsculas, números, _ ou -.")
    if pid in MARKETPLACES:
        raise ValueError("O identificador conflita com um perfil nativo.")
    if not isinstance(name, str) or not 2 <= len(name.strip()) <= 80:
        raise ValueError("Informe um nome de perfil entre 2 e 80 caracteres.")
    terms = obj.get("match_terms", [])
    if (
        not isinstance(terms, list)
        or len(terms) > 30
        or any(not isinstance(x, str) or not 2 <= len(x) <= 100 for x in terms)
    ):
        raise ValueError("match_terms deve ser uma lista de até 30 textos curtos.")
    labels = obj.get("field_labels", {})
    if not isinstance(labels, dict) or set(labels) - set(FIELD_LABELS):
        raise ValueError("field_labels contém campos não suportados.")
    clean_labels: dict[str, list[str]] = {}
    for key, variants in labels.items():
        if (
            not isinstance(variants, list)
            or len(variants) > 20
            or any(not isinstance(x, str) or not 1 <= len(x) <= 100 for x in variants)
        ):
            raise ValueError(f"Rótulos inválidos para {key}.")
        clean_labels[key] = variants
    version = obj.get("version", 1)
    if version != 1:
        raise ValueError("Versão de perfil não suportada.")
    return {
        "schema": PROFILE_SCHEMA,
        "profile_id": pid,
        "name": name.strip(),
        "version": 1,
        "match_terms": terms,
        "field_labels": clean_labels,
    }


def save_profile(obj: Any) -> dict[str, Any]:
    clean = validate_profile(obj)
    path = _profile_dir() / f"{clean['profile_id']}.json"
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return clean


def delete_profile(profile_id: str) -> bool:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,49}", profile_id):
        return False
    if profile_id in MARKETPLACES:
        return False
    path = _profile_dir() / f"{profile_id}.json"
    if not path.is_file():
        return False
    path.unlink()
    return True


def _custom_profiles() -> list[dict[str, Any]]:
    result = []
    for path in _profile_dir().glob("*.json"):
        try:
            result.append(validate_profile(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, TypeError):
            continue
    return result


def detect_profile(text: str, selected: str | None = None) -> dict[str, Any]:
    norm = _normalize(text)
    candidates = [
        {
            "profile_id": key,
            "name": profile["name"],
            "terms": profile["terms"],
            "field_labels": profile.get("field_labels", {}),
        }
        for key, profile in MARKETPLACES.items()
    ]
    candidates.extend(
        {
            "name": p["name"],
            "profile_id": p["profile_id"],
            "terms": p["match_terms"],
            "field_labels": p["field_labels"],
        }
        for p in _custom_profiles()
    )
    scored = []
    for p in candidates:
        hits = sum(1 for term in p.get("terms", []) if _normalize(term) in norm)
        is_builtin = p["profile_id"] in MARKETPLACES
        score = min(1.0, hits / (1 if is_builtin else 2))
        scored.append((score, hits, p))
    scored.sort(key=lambda row: row[0], reverse=True)
    top = next((p for _, _, p in scored if p["profile_id"] == selected), None)
    if top and selected:
        return {
            "profile_id": top["profile_id"],
            "name": top["name"],
            "confidence": 1.0,
            "selected": True,
        }
    best_score, best_hits, best = scored[0] if scored else (0, 0, {})
    second = scored[1][0] if len(scored) > 1 else 0
    min_hits = 1 if best.get("profile_id") in MARKETPLACES else 2
    if best_score < 0.7 or best_hits < min_hits or best_score - second < 0.2:
        return {
            "profile_id": None,
            "name": "Não identificado",
            "confidence": best_score,
            "selected": False,
        }
    return {
        "profile_id": best["profile_id"],
        "name": best["name"],
        "confidence": best_score,
        "selected": False,
    }


def _profile_labels(profile_id: str | None) -> dict[str, list[str]]:
    labels = {k: list(v) for k, v in FIELD_LABELS.items()}
    if profile_id in MARKETPLACES:
        labels.update(MARKETPLACES[profile_id].get("field_labels", {}))
    if profile_id:
        path = _profile_dir() / f"{profile_id}.json"
        if path.is_file():
            try:
                labels.update(
                    validate_profile(json.loads(path.read_text(encoding="utf-8")))["field_labels"]
                )
            except (OSError, ValueError, TypeError):
                pass
    return labels


def _money(value: str) -> float | None:
    raw = re.sub(r"R\$|\$", "", value, flags=re.IGNORECASE).replace(" ", "")
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


def _extract_labeled(lines: list[str], labels: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for field, variants in labels.items():
        normalized_variants = sorted((_normalize(x) for x in variants), key=len, reverse=True)
        for i, line in enumerate(lines):
            normalized_line = _normalize(line)
            matched = next(
                (
                    label
                    for label in normalized_variants
                    if re.match(rf"^{re.escape(label)}(?:\b|\s|:|#|-)", normalized_line)
                ),
                None,
            )
            if not matched:
                continue
            value_part = normalized_line[len(matched):].strip(" :#-\t")
            if not value_part and i + 1 < len(lines):
                value_part = _normalize(lines[i + 1])
            if not value_part:
                continue
            if field in {"total", "subtotal", "shipping", "discount", "tax"}:
                match = re.fullmatch(rf"\s*({MONEY})\s*", value_part, re.I)
                value = _money(match.group(1)) if match else None
            elif field == "date":
                date_match = re.fullmatch(
                    r"(?:data (?:do pedido|da compra|do documento)|order date|purchase date)"
                    r"\s*[:#-]?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                    normalized_line,
                )
                value = date_match.group(1) if date_match else None
            else:
                value = line[len(matched):].strip(" :#-\t")[:160]
            if value not in (None, ""):
                output[field] = {"value": value, "confidence": 0.78, "source": "label"}
                break
    return output


def _extract_items(lines: list[str]) -> list[dict[str, Any]]:
    items = []
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
    return items[:100]


def _parse_nfe_xml(data: bytes) -> dict[str, Any]:
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("XML com declarações externas não é aceito.")
    root = ET.fromstring(data)  # noqa: S314 - DTD/entities are rejected above; NF-e has a fixed local schema.

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    def one(name: str, within: ET.Element | None = None) -> str | None:
        parent = within or root
        node = next((n for n in parent.iter() if local(n.tag) == name), None)
        return node.text.strip() if node is not None and node.text else None

    supplier = one("xNome")
    access = one("chNFe")
    if not access:
        inf = next((node for node in root.iter() if local(node.tag) == "infNFe"), None)
        if inf is not None:
            identity = inf.attrib.get("Id", "")
            access = identity[3:] if identity.startswith("NFe") else None
    number = one("nNF")
    total = one("vNF")
    issue_date = one("dhEmi") or one("dEmi")
    freight = one("vFrete")
    discount = one("vDesc")
    tax = one("vTotTrib")
    items = []
    for det in (n for n in root.iter() if local(n.tag) == "det"):
        prod = next((n for n in det if local(n.tag) == "prod"), None)
        if prod is None:
            continue
        vals = {local(n.tag): n.text.strip() for n in prod if n.text}
        try:
            items.append(
                {
                    "description": vals.get("xProd", "")[:200],
                    "sku": vals.get("cProd", "")[:80],
                    "quantity": float(vals.get("qCom", "0")),
                    "unit_cost": round(float(vals.get("vUnCom", "0")), 4),
                    "line_total": round(float(vals.get("vProd", "0")), 2),
                    "confidence": 1.0,
                }
            )
        except ValueError:
            continue
    fields = {}
    if supplier:
        fields["supplier"] = {"value": supplier, "confidence": 1.0, "source": "xml"}
    if number:
        fields["order_number"] = {"value": number, "confidence": 1.0, "source": "xml"}
    if total:
        fields["total"] = {"value": round(float(total), 2), "confidence": 1.0, "source": "xml"}
    if access:
        fields["access_key"] = {"value": access, "confidence": 1.0, "source": "xml"}
    if issue_date:
        fields["date"] = {"value": issue_date[:10], "confidence": 1.0, "source": "xml"}
    for field, value in (("shipping", freight), ("discount", discount), ("tax", tax)):
        if value:
            fields[field] = {"value": round(float(value), 2), "confidence": 1.0, "source": "xml"}
    return {"fields": fields, "items": items, "warnings": []}


def _extract_text(filename: str, content: bytes) -> tuple[str, str]:
    ext = Path(filename).suffix.lower()
    if ext == ".xml":
        return "", "xml"
    if ext == ".pdf":
        with tempfile.TemporaryDirectory(prefix="purchase-ocr-") as td:
            path = Path(td) / "document.pdf"
            path.write_bytes(content)
            pdfinfo, pdftotext = shutil.which("pdfinfo"), shutil.which("pdftotext")
            if not pdfinfo or not pdftotext:
                raise RuntimeError(
                    "Leitura de PDF indisponível: instale poppler-utils no ambiente local."
                )
            # Executable paths come only from PATH; arguments and temp paths are fixed/validated.
            info = subprocess.run(  # noqa: S603
                [pdfinfo, str(path)], capture_output=True, text=True, timeout=15, check=True
            ).stdout
            pages = re.search(r"^Pages:\s+(\d+)", info, re.M)
            if not pages or int(pages.group(1)) > MAX_PDF_PAGES:
                raise ValueError(f"O PDF deve ter no máximo {MAX_PDF_PAGES} páginas.")
            txt = subprocess.run(  # noqa: S603
                [pdftotext, "-layout", str(path), "-"],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            ).stdout
            if txt.strip():
                return txt, "pdf_text"
            return _ocr_image_or_pdf(path, pdf=True), "ocr"
    if ext not in {".jpg", ".jpeg", ".png"}:
        raise ValueError("Formato não suportado. Use PDF, JPG, PNG ou XML de NF-e.")
    return _ocr_image_or_pdf(content), "ocr"


def _ocr_image_or_pdf(value: Any, pdf: bool = False) -> str:
    tesseract = shutil.which("tesseract")
    if not tesseract:
        raise RuntimeError(
            "OCR local indisponível: instale Tesseract e os dados de idioma por+eng."
        )
    with tempfile.TemporaryDirectory(prefix="purchase-ocr-") as td:
        base = Path(td) / "page"
        if pdf:
            pdftoppm = shutil.which("pdftoppm")
            if not pdftoppm:
                raise RuntimeError("OCR de PDF digitalizado indisponível: instale poppler-utils.")
            subprocess.run(  # noqa: S603
                [
                    pdftoppm,
                    "-f",
                    "1",
                    "-l",
                    str(MAX_PDF_PAGES),
                    "-r",
                    "250",
                    "-png",
                    str(value),
                    str(base),
                ],
                capture_output=True,
                timeout=60,
                check=True,
            )
            images = sorted(Path(td).glob("page-*.png"))
        else:
            try:
                with Image.open(io.BytesIO(value)) as opened:
                    if opened.width * opened.height > 30_000_000:
                        raise ValueError("A imagem excede o limite de 30 megapixels.")
                    image = ImageOps.exif_transpose(opened).convert("RGB")
                    image.thumbnail((2600, 2600), Image.Resampling.LANCZOS)
                    image_path = Path(td) / "normalized.png"
                    image.save(image_path, format="PNG", optimize=True)
                    images = [image_path]
            except (OSError, UnidentifiedImageError) as exc:
                raise ValueError("O arquivo não contém uma imagem JPEG ou PNG válida.") from exc
        output = []
        for image in images:
            result = subprocess.run(  # noqa: S603
                [tesseract, str(image), "stdout", "-l", "por+eng", "--psm", "6", "tsv"],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
                env={**os.environ, "OMP_THREAD_LIMIT": "2"},
            )
            rows = csv.DictReader(result.stdout.splitlines(), delimiter="\t")
            grouped: dict[tuple[str, str, str, str], list[str]] = {}
            confidences = []
            for row in rows:
                if row.get("level") != "5" or not row.get("text", "").strip():
                    continue
                key = (
                    row.get("page_num", ""),
                    row.get("block_num", ""),
                    row.get("par_num", ""),
                    row.get("line_num", ""),
                )
                grouped.setdefault(key, []).append(row["text"].strip())
                try:
                    confidence = float(row.get("conf", "-1"))
                    if confidence >= 0:
                        confidences.append(confidence)
                except ValueError:
                    continue
            output.extend(" ".join(words) for words in grouped.values())
            if confidences:
                # A compact OCR quality signal; individual line values remain editable.
                output.append(f"OCR_QUALITY_SIGNAL={sum(confidences) / len(confidences):.1f}")
        return "\n".join(output)


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
        parsed = _parse_nfe_xml(content)
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
    profile = detect_profile(text, selected_profile)
    labels = _profile_labels(profile["profile_id"])
    fields = _extract_labeled(lines, labels)
    for field in fields.values():
        field["confidence"] = round(field["confidence"] * ocr_quality, 2)
        field["source"] = source
    items = _extract_items(lines)
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
    if "total" not in fields:
        warnings.append("Total não identificado; confira o documento antes de continuar.")
    elif items:
        items_total = sum(item["line_total"] for item in items)
        if abs(items_total - fields["total"]["value"]) > 0.03:
            warnings.append(
                "A soma dos itens não fecha com o total do documento; confira frete,"
                " descontos e impostos."
            )
    return {
        "filename": filename,
        "source": source,
        "profile": profile,
        "fields": fields,
        "items": items,
        "warnings": warnings,
    }

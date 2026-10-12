from __future__ import annotations

import csv
import io
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from app.services.purchase_import_base import (
    MAX_PDF_PAGES,
)


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

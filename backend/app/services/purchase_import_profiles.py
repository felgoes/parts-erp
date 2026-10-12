from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from app.services.purchase_import_base import (
    FIELD_LABELS,
    MARKETPLACES,
    PROFILE_SCHEMA,
)


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


def _profile_from_filename(filename: str | None) -> dict[str, str] | None:
    if not filename:
        return None
    stem = _normalize(Path(filename).stem.replace("_", " ").replace("-", " "))
    for key, profile in MARKETPLACES.items():
        if any(_normalize(term) in stem for term in profile["terms"] if len(term) > 3):
            return {"profile_id": key, "name": profile["name"]}
    for custom in _custom_profiles():
        if any(_normalize(term) in stem for term in custom.get("match_terms", []) if len(term) > 3):
            return {"profile_id": custom["profile_id"], "name": custom["name"]}
    return None


def detect_profile(
    text: str, selected: str | None = None, filename: str | None = None
) -> dict[str, Any]:
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
        suggestion = _profile_from_filename(filename)
        if suggestion:
            return {
                "profile_id": suggestion["profile_id"],
                "name": suggestion["name"],
                "confidence": best_score,
                "selected": False,
                "suggested_from": "filename",
            }
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

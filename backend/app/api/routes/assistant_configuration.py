"""Configuração compartilhada, sem expor a credencial ao cliente."""

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.api.deps import require_roles
from app.core.security import encrypt_secret
from app.db.session import get_db
from app.models import User, UserRole
from app.models.assistant import AssistantConfiguration

router = APIRouter(prefix="/assistant/configuration", tags=["Assistente"])
PROVIDERS = frozenset({"openai", "deepseek", "gemini", "anthropic"})
MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
MAX_BODY = 8192


def view(config: AssistantConfiguration | None) -> dict:
    return {
        "provider": config.provider if config else None,
        "model": config.model if config else None,
        "has_api_key": bool(config and config.encrypted_api_key),
    }


async def parse_payload(request: Request) -> dict:
    # Erros de validação genéricos: nunca refletir um corpo que possa conter uma chave.
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY:
            raise HTTPException(status_code=413, detail="Configuração muito grande")
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Configuração inválida") from None
    if not isinstance(payload, dict) or set(payload) - {
        "provider",
        "model",
        "key_action",
        "api_key",
    }:
        raise HTTPException(status_code=400, detail="Configuração inválida")
    return payload


@router.get("")
def get_configuration(
    response: Response,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return view(db.get(AssistantConfiguration, "shared"))


@router.put("")
async def save_configuration(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
) -> dict:
    payload = await parse_payload(request)
    provider, model, action = (
        payload.get("provider"),
        payload.get("model"),
        payload.get("key_action"),
    )
    if not isinstance(provider, str) or provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Provedor não suportado")
    if not isinstance(model, str) or not MODEL.fullmatch(model):
        raise HTTPException(status_code=400, detail="Modelo inválido")
    if action not in ("keep", "replace", "remove"):
        raise HTTPException(status_code=400, detail="Ação de chave inválida")
    key = payload.get("api_key")
    if action == "replace":
        if not isinstance(key, str) or not key.strip() or len(key) > 4096:
            raise HTTPException(status_code=400, detail="Chave inválida")
    elif "api_key" in payload:
        raise HTTPException(status_code=400, detail="Ação de chave inválida")

    config = db.get(AssistantConfiguration, "shared")
    if config and config.provider != provider and action == "keep" and config.encrypted_api_key:
        raise HTTPException(
            status_code=409, detail="Troque ou remova a chave ao trocar de provedor"
        )
    encrypted = None
    if action == "replace":
        try:
            encrypted = encrypt_secret(key.strip())
        except Exception:
            raise HTTPException(
                status_code=503, detail="Não foi possível proteger a chave"
            ) from None
    if config is None:
        config = AssistantConfiguration(id="shared", provider=provider, model=model)
        db.add(config)
    config.provider, config.model = provider, model
    if action != "keep":
        config.encrypted_api_key = encrypted
    try:
        db.commit()
    except (IntegrityError, StaleDataError):
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Configuração alterada; tente novamente"
        ) from None
    response.headers["Cache-Control"] = "no-store"
    return view(config)

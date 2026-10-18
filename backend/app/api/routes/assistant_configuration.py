"""Configuração compartilhada, sem expor a credencial ao cliente."""

import json
import re
import uuid
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.api.deps import require_roles
from app.assistant import budget
from app.assistant.catalog import PROVIDERS as CATALOG
from app.assistant.catalog import catalog_view, price_for
from app.assistant.providers import AssistantProviderError, complete
from app.core.security import encrypt_secret
from app.db.session import get_db
from app.models import User, UserRole
from app.models.assistant import AssistantConfiguration

router = APIRouter(prefix="/assistant/configuration", tags=["Assistente"])
PROVIDERS = frozenset({"openai", "deepseek", "gemini", "anthropic"})
MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
MAX_BODY = 8192


def view(config: AssistantConfiguration | None, db: Session) -> dict:
    return {
        "provider": config.provider if config else None,
        "model": config.model if config else None,
        "has_api_key": bool(config and config.encrypted_api_key),
        "budget": budget.state(db, config),
        "providers": catalog_view(),
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
        "monthly_budget_usd",
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
    return view(db.get(AssistantConfiguration, "shared"), db)


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
    budget_value = payload.get("monthly_budget_usd", ...)
    if budget_value is not ...:
        if budget_value is None:
            monthly_budget = None
        else:
            try:
                monthly_budget = Decimal(str(budget_value)).quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError):
                raise HTTPException(status_code=400, detail="Limite mensal inválido") from None
            if monthly_budget < 0 or monthly_budget > Decimal("1000000"):
                raise HTTPException(status_code=400, detail="Limite mensal inválido")
    else:
        monthly_budget = ...

    config = db.get(AssistantConfiguration, "shared")
    if price_for(provider, model) is None:
        raise HTTPException(
            status_code=400, detail="Modelo sem preço de referência; escolha um modelo suportado"
        )
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
    if monthly_budget is not ...:
        config.monthly_budget_usd = monthly_budget
    try:
        db.commit()
    except (IntegrityError, StaleDataError):
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Configuração alterada; tente novamente"
        ) from None
    response.headers["Cache-Control"] = "no-store"
    return view(config, db)


@router.get("/catalog")
def get_catalog(
    _: User = Depends(require_roles(UserRole.admin)),
) -> list[dict]:
    return catalog_view()


@router.post("/test")
async def test_connection(
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> dict:
    payload = await parse_payload(request)
    if set(payload) - {"provider", "model", "api_key"}:
        raise HTTPException(status_code=400, detail="Configuração inválida")
    provider = payload.get("provider")
    model = payload.get("model")
    if provider not in CATALOG or not isinstance(model, str) or price_for(provider, model) is None:
        raise HTTPException(status_code=400, detail="Provedor ou modelo não suportado")
    config = db.get(AssistantConfiguration, "shared")
    key = payload.get("api_key")
    if key is None:
        if config is None or config.provider != provider or not config.encrypted_api_key:
            raise HTTPException(status_code=409, detail="Informe a chave para testar")
        try:
            from app.core.security import decrypt_secret

            key = decrypt_secret(config.encrypted_api_key)
        except Exception:
            raise HTTPException(status_code=409, detail="Salve a chave novamente") from None
    if not isinstance(key, str) or not key.strip() or len(key) > 4096:
        raise HTTPException(status_code=400, detail="Chave inválida")
    usage = None
    tracked = bool(
        config
        and config.provider == provider
        and config.model == model
        and config.monthly_budget_usd
        and config.monthly_budget_usd > 0
    )
    if tracked:
        try:
            usage = budget.reserve(
                db,
                config=config,
                user_id=actor.id,
                conversation_id=None,
                request_id=str(uuid.uuid4()),
                estimated_input_tokens=40,
                max_output_tokens=20,
            )
        except budget.AssistantBudgetError as error:
            raise HTTPException(status_code=402, detail=error.message) from None
    try:
        reply = complete(
            provider,
            model,
            key.strip(),
            [{"role": "user", "content": "Responda apenas OK."}],
        )
    except AssistantProviderError as error:
        if usage is not None:
            budget.release(db, usage)
        raise HTTPException(status_code=error.status_code, detail=error.message) from None
    if usage is not None:
        budget.settle(db, usage, reply.input_tokens, reply.output_tokens)
    return {"ok": True, "provider": provider, "model": model, "reply": reply.content[:80]}

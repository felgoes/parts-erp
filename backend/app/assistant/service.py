"""Ciclo de uma mensagem: orçamento, provedor, ferramentas e persistência."""

import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assistant import budget
from app.assistant.catalog import price_for
from app.assistant.prompt import SYSTEM_PROMPT
from app.assistant.providers import AssistantProviderError, complete
from app.assistant.tools import TOOLS, safe_run
from app.core.security import decrypt_secret
from app.models import User
from app.models.assistant import (
    AssistantConfiguration,
    AssistantConversation,
    AssistantMessage,
)

MAX_STEPS = 4
MAX_HISTORY = 24
PROMPT_CHUNK = 4000


class AssistantServiceError(Exception):
    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _history(db: Session, conversation: AssistantConversation) -> list[dict]:
    rows = list(
        db.scalars(
            select(AssistantMessage)
            .where(AssistantMessage.conversation_id == conversation.id)
            .order_by(AssistantMessage.created_at.desc(), AssistantMessage.id.desc())
            .limit(MAX_HISTORY)
        )
    )
    return [
        {"role": message.role, "content": (message.content or "")[:PROMPT_CHUNK]}
        for message in reversed(rows)
        if message.role in {"user", "assistant"}
    ]


def _estimate_tokens(messages: list[dict]) -> int:
    serialized = json.dumps(messages, ensure_ascii=False, default=lambda item: item.__dict__)
    tools = json.dumps(TOOLS, ensure_ascii=False)
    return max(1, len(serialized) // 3 + len(tools) // 4)


def _assistant_message(conversation: AssistantConversation, content: str) -> AssistantMessage:
    return AssistantMessage(conversation_id=conversation.id, role="assistant", content=content)


def run_turn(db: Session, user: User, conversation: AssistantConversation, text: str) -> dict:
    content = (text or "").strip()
    if not content:
        raise AssistantServiceError("Digite uma mensagem.", 422)
    if len(content) > 4000:
        raise AssistantServiceError("A mensagem passa do limite de 4.000 caracteres.", 422)
    config = db.get(AssistantConfiguration, "shared")
    if config is None or not config.encrypted_api_key:
        raise AssistantServiceError(
            "O assistente ainda não tem provedor e chave configurados em Integrações.", 409
        )
    if price_for(config.provider, config.model) is None:
        raise AssistantServiceError(
            "O modelo configurado não tem preço de referência; escolha um modelo suportado.",
            409,
        )
    try:
        api_key = decrypt_secret(config.encrypted_api_key)
    except Exception:
        raise AssistantServiceError(
            "Não foi possível ler a credencial configurada; salve a chave novamente.", 409
        ) from None

    user_message = AssistantMessage(
        conversation_id=conversation.id, role="user", content=content
    )
    db.add(user_message)
    if conversation.title == "Nova conversa":
        conversation.title = content[:80]
    db.commit()

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(_history(db, conversation))
    pending: list[dict] = []
    used_provider = config.provider
    used_model = config.model

    for _ in range(MAX_STEPS):
        estimated = _estimate_tokens(messages)
        usage = None
        try:
            usage = budget.reserve(
                db,
                config=config,
                user_id=user.id,
                conversation_id=conversation.id,
                request_id=str(uuid.uuid4()),
                estimated_input_tokens=estimated,
                max_output_tokens=1200,
            )
        except budget.AssistantBudgetError as error:
            raise AssistantServiceError(error.message, 402) from None

        try:
            reply = complete(used_provider, used_model, api_key, messages, TOOLS)
        except AssistantProviderError as error:
            budget.release(db, usage)
            raise AssistantServiceError(error.message, error.status_code) from None
        except Exception:
            budget.release(db, usage)
            raise AssistantServiceError("Falha inesperada ao falar com o provedor.", 502) from None
        budget.settle(db, usage, reply.input_tokens, reply.output_tokens)

        if not reply.tool_calls:
            final = reply.content.strip() or "Não consegui formular uma resposta."
            db.add(_assistant_message(conversation, final))
            db.commit()
            return {
                "message": final,
                "pending_actions": pending,
                "provider": used_provider,
                "model": used_model,
                "budget": budget.state(db, config),
            }

        messages.append(
            {"role": "assistant", "content": reply.content, "tool_calls": reply.tool_calls}
        )
        for call in reply.tool_calls:
            result = safe_run(
                db,
                conversation=conversation,
                user=user,
                name=call.name,
                args=call.arguments,
            )
            if result.get("status") == "pending_confirmation":
                pending.append(result)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "tool_name": call.name,
                    "content": json.dumps(result, ensure_ascii=False)[:6000],
                }
            )

    final = (
        "Não consegui concluir a solicitação dentro do limite de etapas. "
        "Tente dividir o pedido em partes menores."
    )
    db.add(_assistant_message(conversation, final))
    db.commit()
    return {
        "message": final,
        "pending_actions": pending,
        "provider": used_provider,
        "model": used_model,
        "budget": budget.state(db, config),
    }

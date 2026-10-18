"""Conversa com o assistente e confirmação das ações propostas."""

import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.routes.assistant_history import owned_conversation
from app.assistant import actions
from app.assistant.service import AssistantServiceError, run_turn
from app.db.session import get_db
from app.models import User, UserRole
from app.models.assistant import AssistantMessage, AssistantPendingAction

router = APIRouter(prefix="/assistant", tags=["Assistente"])
MAX_BODY = 16_384


async def _json_body(request: Request) -> dict:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY:
            raise HTTPException(status_code=413, detail="Mensagem muito grande")
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Mensagem inválida") from None
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Mensagem inválida")
    return payload


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin)),
) -> dict:
    conversation = owned_conversation(db, user, conversation_id)
    payload = await _json_body(request)
    if set(payload) - {"message"}:
        raise HTTPException(status_code=400, detail="Mensagem inválida")
    try:
        result = run_turn(db, user, conversation, str(payload.get("message") or ""))
    except AssistantServiceError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from None
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/conversations/{conversation_id}/actions")
def list_actions(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin)),
) -> list[dict]:
    owned_conversation(db, user, conversation_id)
    rows = db.scalars(
        select(AssistantPendingAction)
        .where(
            AssistantPendingAction.conversation_id == conversation_id,
            AssistantPendingAction.user_id == user.id,
            AssistantPendingAction.status.in_(("pending", "stale")),
        )
        .order_by(AssistantPendingAction.created_at.desc())
    )
    return [actions.action_view(row) for row in rows]


@router.post("/actions/{action_id}/confirm")
def confirm_action(
    action_id: str,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin)),
) -> dict:
    action = actions.pending_action(db, user, action_id)
    try:
        result = actions.execute(db, user, action)
    except actions.ActionError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from None
    text = result.get("message") or "Ação concluída."
    detail = f"{text}\n\nPrévia confirmada: {action.summary}"
    db.add(
        AssistantMessage(
            conversation_id=action.conversation_id, role="assistant", content=detail
        )
    )
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return {"action": actions.action_view(action), "result": result, "message": detail}


@router.post("/actions/{action_id}/cancel")
def cancel_action(
    action_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin)),
) -> dict:
    action = actions.pending_action(db, user, action_id)
    return actions.cancel(db, user, action)

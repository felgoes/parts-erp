"""Conversas privadas de cada administrador."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_roles
from app.db.session import get_db
from app.models import User, UserRole
from app.models.assistant import AssistantConversation
from app.schemas.base import ORMModel

router = APIRouter(prefix="/assistant/conversations", tags=["Assistente"])


class ConversationSummary(ORMModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class MessageOut(ORMModel):
    id: str
    role: str
    content: str
    created_at: datetime


class ConversationOut(ConversationSummary):
    messages: list[MessageOut]


def owned_conversation(db: Session, user: User, conversation_id: str) -> AssistantConversation:
    item = db.scalar(
        select(AssistantConversation)
        .where(
            AssistantConversation.id == conversation_id, AssistantConversation.user_id == user.id
        )
        .options(selectinload(AssistantConversation.messages))
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    return item


@router.get("", response_model=list[ConversationSummary])
def list_conversations(
    db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.admin))
) -> list[AssistantConversation]:
    return list(
        db.scalars(
            select(AssistantConversation)
            .where(AssistantConversation.user_id == user.id)
            .order_by(AssistantConversation.updated_at.desc(), AssistantConversation.id)
        )
    )


@router.post("", response_model=ConversationSummary, status_code=201)
def create_conversation(
    db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.admin))
) -> AssistantConversation:
    item = AssistantConversation(user_id=user.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/{conversation_id}", response_model=ConversationOut)
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin)),
) -> AssistantConversation:
    return owned_conversation(db, user, conversation_id)


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin)),
) -> Response:
    db.delete(owned_conversation(db, user, conversation_id))
    db.commit()
    return Response(status_code=204)

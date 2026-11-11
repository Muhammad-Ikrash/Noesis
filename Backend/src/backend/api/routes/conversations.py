import uuid

from fastapi import APIRouter, HTTPException, status

from backend.api.dependencies import CurrentUser, DbSession
from backend.models import Conversation
from backend.schemas.conversation import (
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ConversationUpdate,
    MessageOut,
)
from backend.services import conversation_service
from backend.services.conversation_service import NotFoundError

router = APIRouter(prefix="/conversations", tags=["conversations"])


def owned_conversation(
    db: DbSession, user: CurrentUser, conversation_id: uuid.UUID
) -> Conversation:
    try:
        return conversation_service.get_conversation(db, user.id, conversation_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


def _detail(db: DbSession, conv: Conversation) -> ConversationDetail:
    out = ConversationOut.model_validate(conv)
    messages = [
        MessageOut.model_validate(m)
        for m in conversation_service.list_messages(db, conv.id)
    ]
    return ConversationDetail(**out.model_dump(), messages=messages)


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(
    body: ConversationCreate, db: DbSession, user: CurrentUser
) -> ConversationOut:
    try:
        conv = conversation_service.create_conversation(
            db,
            owner_id=user.id,
            title=body.title,
            document_ids=body.document_ids,
            mode=body.mode,
            retrieval_scope=body.retrieval_scope or user.default_retrieval_scope,
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return ConversationOut.model_validate(conv)


@router.get("", response_model=list[ConversationOut])
def list_conversations(db: DbSession, user: CurrentUser) -> list[ConversationOut]:
    return [
        ConversationOut.model_validate(c)
        for c in conversation_service.list_conversations(db, user.id)
    ]


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> ConversationDetail:
    return _detail(db, owned_conversation(db, user, conversation_id))


@router.patch("/{conversation_id}", response_model=ConversationOut)
def update_conversation(
    conversation_id: uuid.UUID,
    body: ConversationUpdate,
    db: DbSession,
    user: CurrentUser,
) -> ConversationOut:
    conv = owned_conversation(db, user, conversation_id)
    try:
        conv = conversation_service.update_conversation(
            db, conv, **body.model_dump(exclude_unset=True)
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return ConversationOut.model_validate(conv)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> None:
    conversation_service.delete_conversation(
        db, owned_conversation(db, user, conversation_id)
    )

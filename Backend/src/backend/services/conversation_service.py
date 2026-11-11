import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models import Conversation, Document, Message
from backend.models.enums import LearningMode, MessageRole, RetrievalScope
from backend.rag.interfaces import ChatMessage
from backend.services.document_service import get_owned_documents

MAX_HISTORY_CHARS_PER_MESSAGE = 2000
DEFAULT_TITLE = "New chat"


class NotFoundError(Exception):
    pass


def _owned_documents_or_raise(db: Session, owner_id: uuid.UUID, ids: list[uuid.UUID]) -> list[Document]:
    unique = list(dict.fromkeys(ids))
    docs = get_owned_documents(db, owner_id, unique)
    if len(docs) != len(unique):
        # Same error for "does not exist" and "belongs to someone else".
        raise NotFoundError("One or more documents were not found.")
    return docs


def create_conversation(
    db: Session,
    *,
    owner_id: uuid.UUID,
    title: str | None,
    document_ids: list[uuid.UUID],
    mode: LearningMode,
    retrieval_scope: RetrievalScope,
) -> Conversation:
    conv = Conversation(
        owner_id=owner_id,
        title=(title or DEFAULT_TITLE).strip()[:255] or DEFAULT_TITLE,
        mode=mode,
        retrieval_scope=retrieval_scope,
        documents=_owned_documents_or_raise(db, owner_id, document_ids),
    )
    db.add(conv)
    db.commit()
    return conv


def list_conversations(db: Session, owner_id: uuid.UUID) -> list[Conversation]:
    return list(
        db.scalars(
            select(Conversation)
            .where(Conversation.owner_id == owner_id)
            .options(selectinload(Conversation.documents))
            .order_by(Conversation.updated_at.desc())
        )
    )


def get_conversation(db: Session, owner_id: uuid.UUID, conversation_id: uuid.UUID) -> Conversation:
    conv = db.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.owner_id == owner_id)
        .options(selectinload(Conversation.documents))
    )
    if conv is None:
        raise NotFoundError("Conversation not found.")
    return conv


def list_messages(db: Session, conversation_id: uuid.UUID) -> list[Message]:
    return list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .options(selectinload(Message.sources))
            .order_by(Message.created_at)
        )
    )


def update_conversation(
    db: Session,
    conv: Conversation,
    *,
    title: str | None = None,
    mode: LearningMode | None = None,
    retrieval_scope: RetrievalScope | None = None,
    document_ids: list[uuid.UUID] | None = None,
) -> Conversation:
    if title is not None and title.strip():
        conv.title = title.strip()[:255]
    if mode is not None:
        conv.mode = mode
    if retrieval_scope is not None:
        conv.retrieval_scope = retrieval_scope
    if document_ids is not None:
        conv.documents = _owned_documents_or_raise(db, conv.owner_id, document_ids)
    db.commit()
    return conv


def delete_conversation(db: Session, conv: Conversation) -> None:
    db.delete(conv)
    db.commit()


def recent_history(db: Session, conversation_id: uuid.UUID, limit: int) -> list[Message]:
    if limit <= 0:
        return []
    rows = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    ).all()
    return list(reversed(rows))


def history_as_chat(messages: list[Message]) -> list[ChatMessage]:
    out = []
    for m in messages:
        content = m.content
        if m.role is MessageRole.ASSISTANT and m.supplementary:
            content = f"{content}\n\nAdditional explanation: {m.supplementary}"
        out.append(ChatMessage(m.role.value, content[:MAX_HISTORY_CHARS_PER_MESSAGE]))
    return out

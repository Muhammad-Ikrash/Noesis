import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.database.base import utcnow
from backend.models import Conversation, Message, MessageSource
from backend.models.enums import (
    DocumentStatus,
    LearningMode,
    MessageRole,
    RetrievalScope,
)
from backend.rag.interfaces import EmbeddingProvider, LLMProvider
from backend.rag.pipeline import (
    NormalizedAnswer,
    build_messages,
    no_sources_answer,
    normalize,
)
from backend.services.conversation_service import (
    DEFAULT_TITLE,
    history_as_chat,
    recent_history,
)
from backend.services.retrieval import RetrievedChunk, build_retrieval_query, retrieve


@dataclass
class AnswerResult:
    user_message: Message
    assistant_message: Message
    answer: NormalizedAnswer
    retrieved: list[RetrievedChunk]
    scope: RetrievalScope
    searched_document_count: int | None


def ask(
    db: Session,
    *,
    conversation: Conversation,
    question: str,
    mode: LearningMode,
    scope: RetrievalScope | None,
    llm: LLMProvider,
    embedder: EmbeddingProvider,
    settings: Settings,
) -> AnswerResult:
    """Answer one question. Ownership of `conversation` must already be verified by the caller."""
    question = question.strip()
    scope = scope or conversation.retrieval_scope

    history = recent_history(db, conversation.id, settings.history_max_messages)
    previous_questions = (
        [m.content for m in history if m.role is MessageRole.USER][
            -settings.query_history_turns :
        ]
        if settings.query_history_turns
        else []
    )

    # Retrieval runs on every turn; earlier turns' chunks are never reused as evidence.
    if scope is RetrievalScope.SESSION:
        document_ids: list[uuid.UUID] | None = [
            d.id for d in conversation.documents if d.status is DocumentStatus.COMPLETED
        ]
        searched = len(document_ids)
    else:
        document_ids, searched = None, None
    chunks = retrieve(
        db,
        embedder,
        owner_id=conversation.owner_id,
        query=build_retrieval_query(question, previous_questions),
        document_ids=document_ids,
        top_k=settings.retrieval_top_k,
    )

    if not chunks and mode is LearningMode.BASIC:
        answer = no_sources_answer()
    else:
        result = llm.complete(
            build_messages(mode, history_as_chat(history), question, chunks),
            json_mode=True,
        )
        answer = normalize(result.text, mode, chunks)

    now = utcnow()
    user_msg = Message(
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content=question,
        mode=mode,
        retrieval_scope=scope,
        created_at=now,
    )
    assistant_msg = Message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=answer.answer,
        supplementary=answer.supplementary,
        mode=mode,
        retrieval_scope=scope,
        answer_status=answer.status,
        needs_clarification=answer.needs_clarification,
        clarification_question=answer.clarification_question,
        created_at=now + timedelta(microseconds=1),
        sources=[
            MessageSource(
                position=i + 1,
                chunk_id=c.chunk.chunk_id,
                document_id=c.chunk.document_id,
                filename=c.chunk.filename,
                page_number=c.chunk.page_number,
                quote=c.quote,
                score=c.chunk.score,
            )
            for i, c in enumerate(answer.citations)
        ],
    )
    db.add_all([user_msg, assistant_msg])
    conversation.mode = mode
    conversation.retrieval_scope = scope
    conversation.last_message_at = now
    if conversation.title == DEFAULT_TITLE:
        conversation.title = question[:80]
    db.commit()
    return AnswerResult(user_msg, assistant_msg, answer, chunks, scope, searched)

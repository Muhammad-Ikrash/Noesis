import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.models.enums import AnswerStatus, LearningMode, MessageRole, RetrievalScope
from backend.schemas.document import DocumentOut


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    mode: LearningMode = LearningMode.BASIC
    # Omit to use the student's default from /settings.
    retrieval_scope: RetrievalScope | None = None


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    mode: LearningMode | None = None
    retrieval_scope: RetrievalScope | None = None
    # Replaces the attached set when provided.
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    document_id: uuid.UUID | None  # null if the document has since been deleted
    chunk_id: uuid.UUID | None
    filename: str
    page_number: int
    quote: str | None
    score: float | None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: MessageRole
    content: str
    supplementary: str | None
    mode: LearningMode
    retrieval_scope: RetrievalScope | None
    answer_status: AnswerStatus | None
    needs_clarification: bool
    clarification_question: str | None
    created_at: datetime
    sources: list[SourceOut]


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    mode: LearningMode
    retrieval_scope: RetrievalScope
    documents: list[DocumentOut]
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]

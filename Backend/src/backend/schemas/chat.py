import uuid

from pydantic import BaseModel, Field

from backend.models.enums import AnswerStatus, LearningMode, RetrievalScope
from backend.schemas.conversation import MessageOut, SourceOut


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    mode: LearningMode
    # The per-chat slider. Omit to keep the conversation's current scope; a value is saved on the chat.
    retrieval_scope: RetrievalScope | None = None


class RetrievedOut(BaseModel):
    """Diagnostics: every chunk retrieved for this turn, cited or not."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_number: int
    score: float


class AskResponse(BaseModel):
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    mode: LearningMode
    retrieval_scope: RetrievalScope
    answer_status: AnswerStatus
    answer: str
    supplementary: str | None
    needs_clarification: bool
    clarification_question: str | None
    sources: list[SourceOut]
    retrieved: list[RetrievedOut]
    # Completed PDFs searched in session scope; null in library scope.
    searched_document_count: int | None
    user_message: MessageOut

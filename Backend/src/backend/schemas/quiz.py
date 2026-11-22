import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.models.enums import QuestionKind, QuizDifficulty

# Answer to one question: an option index, a list of indexes (multiple choice), or null = skipped.
Answer = int | list[int] | None


class QuizCreate(BaseModel):
    # Either explicit documents, or a conversation whose attached PDFs are used.
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    conversation_id: uuid.UUID | None = None
    topic: str | None = Field(default=None, max_length=500)
    question_count: int = Field(default=5, ge=1, le=15)
    difficulty: QuizDifficulty = QuizDifficulty.MEDIUM
    # Kinds the quiz may mix; at least one.
    question_types: list[QuestionKind] = Field(
        default_factory=lambda: [QuestionKind.SINGLE], min_length=1, max_length=3
    )


class QuestionOut(BaseModel):
    """Shown while attempting: no answer key."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    kind: QuestionKind
    prompt: str
    options: list[str]
    filename: str
    page_number: int


class QuestionReview(QuestionOut):
    correct_indices: list[int]
    correct_index: int
    explanation: str
    document_id: uuid.UUID | None
    chunk_id: uuid.UUID | None


class AttemptSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    score: int
    total: int
    created_at: datetime


class QuizSummary(BaseModel):
    id: uuid.UUID
    title: str
    topic: str | None
    difficulty: QuizDifficulty
    conversation_id: uuid.UUID | None
    question_count: int
    best_score: int | None
    attempt_count: int
    created_at: datetime


class QuizOut(BaseModel):
    id: uuid.UUID
    title: str
    topic: str | None
    difficulty: QuizDifficulty
    conversation_id: uuid.UUID | None
    created_at: datetime
    questions: list[QuestionOut]
    attempts: list[AttemptSummary]


class AttemptCreate(BaseModel):
    answers: list[Answer] = Field(max_length=15)


class AttemptResult(BaseModel):
    id: uuid.UUID
    quiz_id: uuid.UUID
    score: int
    total: int
    answers: list[Answer]
    created_at: datetime
    questions: list[QuestionReview]

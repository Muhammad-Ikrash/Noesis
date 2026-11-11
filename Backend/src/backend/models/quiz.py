import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base, UUIDPk, utcnow


class Quiz(UUIDPk, Base):
    __tablename__ = "quizzes"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    topic: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    questions: Mapped[list["QuizQuestion"]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QuizQuestion.position",
    )
    attempts: Mapped[list["QuizAttempt"]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QuizAttempt.created_at.desc()",
    )


class QuizQuestion(UUIDPk, Base):
    """Each question snapshots its source so it stays reviewable after the PDF is deleted."""

    __tablename__ = "quiz_questions"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quizzes.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(JSONB)
    correct_index: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL")
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    filename: Mapped[str] = mapped_column(String(512))
    page_number: Mapped[int] = mapped_column(Integer)


class QuizAttempt(UUIDPk, Base):
    __tablename__ = "quiz_attempts"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quizzes.id", ondelete="CASCADE"), index=True
    )
    # One entry per question, in order; null = skipped.
    answers: Mapped[list[int | None]] = mapped_column(JSONB)
    score: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

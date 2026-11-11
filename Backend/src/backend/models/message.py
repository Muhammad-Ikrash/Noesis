import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base, UUIDPk, utcnow
from backend.models.enums import AnswerStatus, LearningMode, MessageRole, RetrievalScope


def _values(e: type) -> list[str]:
    return [m.value for m in e]


class Message(UUIDPk, Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole, name="message_role", values_callable=_values))
    content: Mapped[str] = mapped_column(Text)
    # Extensive mode only: explanation not established by the PDFs.
    supplementary: Mapped[str | None] = mapped_column(Text)
    mode: Mapped[LearningMode] = mapped_column(
        Enum(LearningMode, name="learning_mode", values_callable=_values, create_type=False)
    )
    retrieval_scope: Mapped[RetrievalScope | None] = mapped_column(
        Enum(RetrievalScope, name="retrieval_scope", values_callable=_values, create_type=False)
    )
    answer_status: Mapped[AnswerStatus | None] = mapped_column(
        Enum(AnswerStatus, name="answer_status", values_callable=_values)
    )
    needs_clarification: Mapped[bool] = mapped_column(Boolean, default=False)
    clarification_question: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    sources: Mapped[list["MessageSource"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="MessageSource.position"
    )


class MessageSource(UUIDPk, Base):
    """Citation snapshot: filename/page/quote survive even if the document is deleted later."""

    __tablename__ = "message_sources"

    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(512))
    page_number: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(Float)

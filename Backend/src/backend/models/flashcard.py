import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base, UUIDPk, utcnow


class FlashcardDeck(UUIDPk, Base):
    __tablename__ = "flashcard_decks"

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

    cards: Mapped[list["Flashcard"]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Flashcard.position",
    )


class Flashcard(UUIDPk, Base):
    """Each card snapshots its source so it stays reviewable after the PDF is deleted."""

    __tablename__ = "flashcards"

    deck_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("flashcard_decks.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    front: Mapped[str] = mapped_column(Text)
    back: Mapped[str] = mapped_column(Text)
    # Study progress: marked "Got it" the last time it was reviewed.
    known: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL")
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    filename: Mapped[str] = mapped_column(String(512))
    page_number: Mapped[int] = mapped_column(Integer)

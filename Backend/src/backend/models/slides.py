import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base, UUIDPk, utcnow


class SlideDeck(UUIDPk, Base):
    __tablename__ = "slide_decks"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    subtitle: Mapped[str | None] = mapped_column(String(500))
    topic: Mapped[str | None] = mapped_column(String(500))
    # SlideDesign settings; null means the defaults.
    design: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    slides: Mapped[list["Slide"]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Slide.position",
    )


class Slide(UUIDPk, Base):
    """Content slide. `sources` snapshots {document_id, filename, page_number} so a slide
    keeps its citations after the PDF is deleted."""

    __tablename__ = "slides"

    deck_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("slide_decks.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    bullets: Mapped[list[str]] = mapped_column(JSONB)
    notes: Mapped[str] = mapped_column(Text, default="")
    sources: Mapped[list[dict]] = mapped_column(JSONB)

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base, Timestamps, UUIDPk, utcnow
from backend.models.document import Document
from backend.models.enums import LearningMode, RetrievalScope

conversation_documents = Table(
    "conversation_documents",
    Base.metadata,
    Column("conversation_id", ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True),
    Column("document_id", ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
    Column("attached_at", DateTime(timezone=True), default=utcnow),
)


class Conversation(UUIDPk, Timestamps, Base):
    __tablename__ = "conversations"

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    mode: Mapped[LearningMode] = mapped_column(
        Enum(LearningMode, name="learning_mode", values_callable=lambda e: [m.value for m in e]),
        default=LearningMode.BASIC,
    )
    retrieval_scope: Mapped[RetrievalScope] = mapped_column(
        Enum(RetrievalScope, name="retrieval_scope", values_callable=lambda e: [m.value for m in e], create_type=False),
        default=RetrievalScope.SESSION,
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    documents: Mapped[list[Document]] = relationship(secondary=conversation_documents)

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base, UUIDPk, utcnow
from backend.models.document import Document
from backend.models.enums import ChunkKind

# Fixed by the migration. Changing it requires a migration plus re-embedding all documents.
EMBEDDING_DIMENSION = 1024


class DocumentChunk(UUIDPk, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index"),
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    # Chunks never cross page boundaries, so one page number is exact.
    page_number: Mapped[int] = mapped_column(Integer)
    kind: Mapped[ChunkKind] = mapped_column(
        Enum(ChunkKind, name="chunk_kind", values_callable=lambda e: [m.value for m in e]),
        default=ChunkKind.TEXT,
    )
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSION))
    embedding_model: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped[Document] = relationship()

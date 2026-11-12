import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.models import Document, DocumentChunk
from backend.models.enums import ChunkKind, DocumentStatus
from backend.rag.interfaces import EmbeddingProvider


class RetrievalError(Exception):
    pass


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_number: int
    kind: ChunkKind
    text: str
    score: float  # cosine similarity, higher is closer


def build_retrieval_query(question: str, previous_user_questions: list[str]) -> str:
    """Fold recent user turns into the query so follow-ups like 'why?' retrieve the right topic."""
    parts = [q.strip() for q in previous_user_questions if q.strip()]
    parts.append(question.strip())
    return "\n".join(parts)


def retrieve(
    db: Session,
    embedder: EmbeddingProvider,
    *,
    owner_id: uuid.UUID,
    query: str,
    document_ids: list[uuid.UUID] | None,
    top_k: int,
    min_score: float = 0.0,
) -> list[RetrievedChunk]:
    """Similarity search restricted to the owner's completed documents.

    document_ids=None searches the owner's whole library; an empty list searches nothing.
    """
    if document_ids is not None and not document_ids:
        return []

    vector = embedder.embed_query(query)
    if len(vector) != embedder.dimension:
        raise RetrievalError(
            f"Query embedding has dimension {len(vector)}, expected {embedder.dimension}."
        )

    distance = DocumentChunk.embedding.cosine_distance(vector).label("distance")
    stmt = (
        select(DocumentChunk, Document.filename, distance)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.owner_id == owner_id, Document.status == DocumentStatus.COMPLETED
        )
        .order_by(distance)
        .limit(top_k)
    )
    if document_ids is not None:
        stmt = stmt.where(Document.id.in_(document_ids))
    if min_score > 0:
        # score = 1 - cosine distance, so "score >= min_score" is "distance <= 1 - min_score".
        stmt = stmt.where(distance <= 1.0 - min_score)

    # Keep scanning the HNSW index until enough rows pass the owner/document filters (pgvector >= 0.8).
    db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    rows = db.execute(stmt).all()
    return [
        RetrievedChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            filename=filename,
            page_number=chunk.page_number,
            kind=chunk.kind,
            text=chunk.text,
            score=1.0 - float(dist),
        )
        for chunk, filename, dist in rows
    ]

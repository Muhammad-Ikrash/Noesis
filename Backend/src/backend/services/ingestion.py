import logging
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from backend.core.config import Settings
from backend.models import Document, DocumentChunk, DocumentPage
from backend.models.enums import DocumentStatus, PageExtraction
from backend.rag.interfaces import EmbeddingProvider, OCRProvider, ProviderError
from backend.services.chunking import chunk_pages
from backend.services.pdf_extraction import PDFExtractionError, extract_pdf
from backend.services.storage import FileStorage

logger = logging.getLogger(__name__)


class IngestionError(Exception):
    """Failure whose message is safe to store and show to the student."""


def _claim(db: Session, document_id: uuid.UUID) -> bool:
    """Atomically move pending -> processing so duplicate submissions do not ingest twice."""
    result = db.execute(
        update(Document)
        .where(Document.id == document_id, Document.status == DocumentStatus.PENDING)
        .values(status=DocumentStatus.PROCESSING, error_message=None)
    )
    db.commit()
    return result.rowcount == 1


def ingest_document(
    document_id: uuid.UUID,
    *,
    session_factory: sessionmaker[Session],
    storage: FileStorage,
    embedder: EmbeddingProvider,
    settings: Settings,
    ocr: OCRProvider | None = None,
) -> None:
    with session_factory() as db:
        if not _claim(db, document_id):
            logger.info("Document %s is not pending; skipping ingestion", document_id)
            return
        doc = db.get(Document, document_id)
        try:
            _ingest(db, doc, storage, embedder, settings, ocr)
        except Exception as exc:
            db.rollback()
            message = (
                str(exc)
                if isinstance(exc, (IngestionError, PDFExtractionError, ProviderError))
                else "Unexpected error while processing the PDF."
            )
            if not isinstance(exc, (IngestionError, PDFExtractionError)):
                logger.exception("Ingestion failed for document %s", document_id)
            db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
            db.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status=DocumentStatus.FAILED, error_message=message)
            )
            db.commit()


def _ingest(
    db: Session,
    doc: Document,
    storage: FileStorage,
    embedder: EmbeddingProvider,
    settings: Settings,
    ocr: OCRProvider | None,
) -> None:
    if embedder.dimension != settings.embedding_dimension:
        raise IngestionError("Embedding dimension does not match configuration.")

    extracted = extract_pdf(str(storage.path_for(doc.storage_key)), min_page_chars=settings.min_page_chars, ocr=ocr)

    # Clear leftovers from an earlier failed attempt before writing.
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
    db.execute(delete(DocumentPage).where(DocumentPage.document_id == doc.id))
    db.add_all(
        DocumentPage(
            document_id=doc.id,
            page_number=p.page_number,
            char_count=len(p.markdown.strip()),
            image_count=p.image_count,
            table_count=p.table_count,
            needs_ocr=p.needs_ocr,
            extraction_method=PageExtraction.OCR if p.ocr_applied else PageExtraction.TEXT,
        )
        for p in extracted.pages
    )
    doc.page_count = extracted.page_count

    if not extracted.has_text:
        db.commit()  # keep page records so the client can show which pages need OCR
        raise IngestionError(
            "No extractable text was found. The PDF appears to be scanned or image-only, and OCR is not enabled."
        )

    chunks = chunk_pages(
        [(p.page_number, p.markdown) for p in extracted.pages if p.markdown.strip()],
        size=settings.chunk_size,
        overlap=settings.chunk_overlap,
    )
    batch = settings.embedding_batch_size
    for start in range(0, len(chunks), batch):
        part = chunks[start : start + batch]
        vectors = embedder.embed_documents([c.text for c in part])
        if len(vectors) != len(part):
            raise IngestionError("The embedding provider returned the wrong number of vectors.")
        for offset, (chunk, vector) in enumerate(zip(part, vectors, strict=True)):
            if len(vector) != settings.embedding_dimension:
                raise IngestionError(
                    f"Embedding dimension mismatch: expected {settings.embedding_dimension}, got {len(vector)}."
                )
            db.add(
                DocumentChunk(
                    document_id=doc.id,
                    chunk_index=start + offset,
                    page_number=chunk.page_number,
                    kind=chunk.kind,
                    text=chunk.text,
                    embedding=vector,
                    embedding_model=embedder.model,
                )
            )

    doc.embedding_model = embedder.model
    doc.status = DocumentStatus.COMPLETED
    db.commit()
    logger.info("Ingested document %s: %d pages, %d chunks", doc.id, extracted.page_count, len(chunks))


def pending_document_ids(db: Session) -> list[uuid.UUID]:
    """Documents to (re)ingest at startup, including ones interrupted mid-processing."""
    db.execute(
        update(Document).where(Document.status == DocumentStatus.PROCESSING).values(status=DocumentStatus.PENDING)
    )
    db.commit()
    return list(db.scalars(select(Document.id).where(Document.status == DocumentStatus.PENDING)))

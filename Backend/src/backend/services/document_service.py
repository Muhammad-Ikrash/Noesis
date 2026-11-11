import hashlib
import logging
import uuid
from dataclasses import dataclass
from pathlib import PurePath

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.models import Document
from backend.models.enums import DocumentStatus
from backend.services.pdf_extraction import looks_like_pdf
from backend.services.storage import FileStorage

logger = logging.getLogger(__name__)


class UploadError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class UploadResult:
    document: Document
    # False when an identical, already-processed PDF was found in the library.
    needs_ingestion: bool


def _display_name(filename: str | None) -> str:
    # Keep only the final path component for display; it is never used as a filesystem path.
    name = PurePath((filename or "").replace("\\", "/")).name.strip()
    return name[:512] or "document.pdf"


def upload_document(
    db: Session,
    storage: FileStorage,
    *,
    owner_id: uuid.UUID,
    filename: str | None,
    data: bytes,
    max_bytes: int,
) -> UploadResult:
    display = _display_name(filename)
    if not display.lower().endswith(".pdf"):
        raise UploadError("Only .pdf files are accepted.", 415)
    if not data:
        raise UploadError("The uploaded file is empty.")
    if len(data) > max_bytes:
        raise UploadError(f"The file exceeds the {max_bytes // (1024 * 1024)} MB limit.", 413)
    if not looks_like_pdf(data):
        raise UploadError("The file content is not a PDF.", 415)

    digest = hashlib.sha256(data).hexdigest()
    existing = db.scalar(select(Document).where(Document.owner_id == owner_id, Document.sha256 == digest))
    if existing is not None:
        if existing.status in (DocumentStatus.FAILED, DocumentStatus.MISSING):
            storage.save(existing.storage_key, data)
            existing.status = DocumentStatus.PENDING
            existing.error_message = None
            existing.filename = display
            db.commit()
            return UploadResult(existing, True)
        return UploadResult(existing, False)

    key = storage.new_key()
    storage.save(key, data)
    doc = Document(
        owner_id=owner_id,
        filename=display,
        storage_key=key,
        sha256=digest,
        size_bytes=len(data),
        mime_type="application/pdf",
        status=DocumentStatus.PENDING,
    )
    try:
        db.add(doc)
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key)
        raise
    return UploadResult(doc, True)


def list_documents(db: Session, owner_id: uuid.UUID) -> list[Document]:
    return list(db.scalars(select(Document).where(Document.owner_id == owner_id).order_by(Document.created_at.desc())))


def get_document(db: Session, owner_id: uuid.UUID, document_id: uuid.UUID) -> Document | None:
    return db.scalar(select(Document).where(Document.id == document_id, Document.owner_id == owner_id))


def get_owned_documents(db: Session, owner_id: uuid.UUID, ids: list[uuid.UUID]) -> list[Document]:
    if not ids:
        return []
    return list(db.scalars(select(Document).where(Document.owner_id == owner_id, Document.id.in_(ids))))


def delete_document(db: Session, storage: FileStorage, doc: Document) -> None:
    """Chunks, pages and chat attachments cascade; message citations keep their snapshot."""
    key = doc.storage_key
    db.delete(doc)
    db.commit()
    try:
        storage.delete(key)
    except OSError:
        logger.warning("Could not remove stored file for deleted document %s", doc.id)


def mark_missing_files(db: Session, storage: FileStorage) -> int:
    """Startup check: flag documents whose stored PDF is gone. Embeddings are kept."""
    missing = [
        d.id
        for d in db.scalars(select(Document).where(Document.status != DocumentStatus.MISSING))
        if not storage.exists(d.storage_key)
    ]
    if missing:
        db.execute(update(Document).where(Document.id.in_(missing)).values(status=DocumentStatus.MISSING))
        db.commit()
        logger.warning("%d document(s) have no stored file and were marked missing", len(missing))
    return len(missing)

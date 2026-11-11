import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse

from backend.api.dependencies import (
    AppSettings,
    CurrentUser,
    DbSession,
    IngestorDep,
    Storage,
)
from backend.schemas.document import DocumentDetail, DocumentOut, UploadOut
from backend.services import document_service
from backend.services.document_service import UploadError

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=UploadOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile,
    response: Response,
    background: BackgroundTasks,
    db: DbSession,
    user: CurrentUser,
    storage: Storage,
    settings: AppSettings,
    ingest: IngestorDep,
) -> UploadOut:
    """Upload a PDF to the library. Ingestion runs in the background; poll GET /documents/{id}."""
    # Read one byte past the limit so oversized files are rejected without buffering everything.
    data = await file.read(settings.max_upload_bytes + 1)
    try:
        result = document_service.upload_document(
            db,
            storage,
            owner_id=user.id,
            filename=file.filename,
            data=data,
            max_bytes=settings.max_upload_bytes,
        )
    except UploadError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    if result.needs_ingestion:
        background.add_task(ingest, result.document.id)
    else:
        response.status_code = status.HTTP_200_OK
    return UploadOut(
        document=DocumentOut.model_validate(result.document),
        created=result.needs_ingestion,
    )


@router.get("", response_model=list[DocumentOut])
def list_documents(db: DbSession, user: CurrentUser) -> list[DocumentOut]:
    return [
        DocumentOut.model_validate(d)
        for d in document_service.list_documents(db, user.id)
    ]


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> DocumentDetail:
    doc = document_service.get_document(db, user.id, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    return DocumentDetail.model_validate(doc)


@router.get("/{document_id}/file", response_class=FileResponse)
def get_document_file(
    document_id: uuid.UUID, db: DbSession, user: CurrentUser, storage: Storage
) -> FileResponse:
    """Stream the stored PDF for the viewer."""
    doc = document_service.get_document(db, user.id, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    if not storage.exists(doc.storage_key):
        raise HTTPException(status.HTTP_410_GONE, "The stored PDF file is missing.")
    return FileResponse(
        storage.path_for(doc.storage_key),
        media_type="application/pdf",
        filename=doc.filename,
        content_disposition_type="inline",
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID, db: DbSession, user: CurrentUser, storage: Storage
) -> None:
    """Delete the PDF, its chunks/embeddings and chat attachments. Past citations keep filename/page."""
    doc = document_service.get_document(db, user.id, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    document_service.delete_document(db, storage, doc)

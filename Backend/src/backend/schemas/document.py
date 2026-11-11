import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field

from backend.models.enums import DocumentStatus


class DocumentPageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page_number: int
    char_count: int
    image_count: int
    table_count: int
    needs_ocr: bool


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    size_bytes: int
    status: DocumentStatus
    error_message: str | None
    page_count: int | None
    embedding_model: str | None
    created_at: datetime
    updated_at: datetime


class DocumentDetail(DocumentOut):
    pages: list[DocumentPageOut]

    @computed_field
    @property
    def ocr_pages(self) -> list[int]:
        return [p.page_number for p in self.pages if p.needs_ocr]


class UploadOut(BaseModel):
    document: DocumentOut
    # False when the identical PDF was already in the library and was reused.
    created: bool

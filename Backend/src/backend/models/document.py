import uuid

from sqlalchemy import BigInteger, Boolean, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base, Timestamps, UUIDPk
from backend.models.enums import DocumentStatus, PageExtraction


def _values(e: type) -> list[str]:
    return [m.value for m in e]


class Document(UUIDPk, Timestamps, Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("owner_id", "sha256", name="uq_documents_owner_sha256"),)

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(512))
    # Server-generated, relative to STORAGE_DIR. Never exposed through the API.
    storage_key: Mapped[str] = mapped_column(String(128), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    mime_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", values_callable=_values),
        default=DocumentStatus.PENDING,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    embedding_model: Mapped[str | None] = mapped_column(String(255))

    pages: Mapped[list["DocumentPage"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DocumentPage.page_number",
    )


class DocumentPage(UUIDPk, Base):
    """Per-page extraction record; pages with needs_ocr=True are where OCR would plug in."""

    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number"),)

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    page_number: Mapped[int] = mapped_column(Integer)  # one-based
    char_count: Mapped[int] = mapped_column(Integer)
    image_count: Mapped[int] = mapped_column(Integer, default=0)
    table_count: Mapped[int] = mapped_column(Integer, default=0)
    needs_ocr: Mapped[bool] = mapped_column(Boolean, default=False)
    extraction_method: Mapped[PageExtraction] = mapped_column(
        Enum(PageExtraction, name="page_extraction", values_callable=_values),
        default=PageExtraction.TEXT,
    )

    document: Mapped[Document] = relationship(back_populates="pages")

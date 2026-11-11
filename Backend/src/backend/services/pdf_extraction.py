"""Page-wise PDF extraction. Every page keeps its one-based page number."""

import logging
from dataclasses import dataclass, field

import pymupdf
import pymupdf4llm

from backend.rag.interfaces import OCRProvider
from backend.services.chunking import count_tables

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"


class PDFExtractionError(Exception):
    """The file is not a readable PDF."""


@dataclass
class ExtractedPage:
    page_number: int  # one-based
    markdown: str
    image_count: int = 0
    table_count: int = 0
    needs_ocr: bool = False
    ocr_applied: bool = False


@dataclass
class ExtractedDocument:
    pages: list[ExtractedPage] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def has_text(self) -> bool:
        return any(p.markdown.strip() for p in self.pages)

    @property
    def ocr_pages(self) -> list[int]:
        return [p.page_number for p in self.pages if p.needs_ocr]


def looks_like_pdf(head: bytes) -> bool:
    # The PDF spec allows the header within the first 1024 bytes.
    return PDF_MAGIC in head[:1024]


def extract_pdf(
    path: str, *, min_page_chars: int, ocr: OCRProvider | None = None
) -> ExtractedDocument:
    try:
        doc = pymupdf.open(path, filetype="pdf")
    except (
        Exception
    ) as exc:  # PyMuPDF raises several unrelated types for corrupt files.
        raise PDFExtractionError("The file could not be opened as a PDF.") from exc

    with doc:
        if doc.needs_pass:
            raise PDFExtractionError("Password-protected PDFs are not supported.")
        if doc.page_count == 0:
            raise PDFExtractionError("The PDF has no pages.")

        try:
            # use_ocr=False: no OCR runs unless an OCRProvider is configured explicitly.
            chunks = pymupdf4llm.to_markdown(
                doc, page_chunks=True, use_ocr=False, show_progress=False
            )
        except Exception as exc:
            raise PDFExtractionError("Text extraction failed for this PDF.") from exc

        result = ExtractedDocument()
        for index, page in enumerate(doc):
            markdown = chunks[index]["text"] if index < len(chunks) else ""
            if not markdown.strip():
                # Layout analysis occasionally drops text it cannot classify; fall back to raw text.
                markdown = page.get_text("text")
            extracted = ExtractedPage(
                page_number=index + 1,
                markdown=markdown,
                image_count=len(page.get_images(full=False)),
                table_count=count_tables(markdown),
            )
            extracted.needs_ocr = len(markdown.strip()) < min_page_chars
            if extracted.needs_ocr and ocr is not None:
                text = ocr.extract_page_text(page)
                if text.strip():
                    extracted.markdown = text
                    extracted.ocr_applied = True
                    extracted.needs_ocr = False
            result.pages.append(extracted)

    logger.info(
        "Extracted %d pages (%d need OCR)", result.page_count, len(result.ocr_pages)
    )
    return result

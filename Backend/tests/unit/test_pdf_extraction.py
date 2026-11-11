import pytest

from backend.services.pdf_extraction import (
    PDFExtractionError,
    extract_pdf,
    looks_like_pdf,
)
from tests.pdfs import make_pdf


def _write(tmp_path, data: bytes):
    path = tmp_path / "f.pdf"
    path.write_bytes(data)
    return str(path)


def test_text_pdf_extracts_with_one_based_pages(tmp_path):
    path = _write(
        tmp_path,
        make_pdf(["Photosynthesis uses chlorophyll.", "Mitochondria make ATP."]),
    )
    doc = extract_pdf(path, min_page_chars=10)
    assert [p.page_number for p in doc.pages] == [1, 2]
    assert "chlorophyll" in doc.pages[0].markdown.lower()
    assert "atp" in doc.pages[1].markdown.lower()
    assert doc.ocr_pages == []


def test_image_only_page_is_flagged_for_ocr(tmp_path):
    path = _write(tmp_path, make_pdf(["Some real text here on page one.", None]))
    doc = extract_pdf(path, min_page_chars=10)
    assert doc.ocr_pages == [2]
    assert doc.pages[1].image_count == 1
    assert doc.has_text


def test_fully_scanned_pdf_has_no_text(tmp_path):
    doc = extract_pdf(_write(tmp_path, make_pdf([None, None])), min_page_chars=10)
    assert not doc.has_text and doc.ocr_pages == [1, 2]


def test_ocr_provider_hook_fills_flagged_pages(tmp_path):
    class StubOCR:
        def extract_page_text(self, page):
            return "recognised text from the image"

    doc = extract_pdf(
        _write(tmp_path, make_pdf([None])), min_page_chars=10, ocr=StubOCR()
    )
    assert doc.pages[0].ocr_applied and not doc.pages[0].needs_ocr


def test_corrupt_pdf_raises(tmp_path):
    with pytest.raises(PDFExtractionError):
        extract_pdf(
            _write(tmp_path, b"%PDF-1.7 garbage that is not a pdf"), min_page_chars=10
        )


def test_magic_bytes_check():
    assert looks_like_pdf(make_pdf(["x"]))
    assert not looks_like_pdf(b"PK\x03\x04 zip file")

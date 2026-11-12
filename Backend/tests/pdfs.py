import pymupdf


def make_pdf(pages: list[str | None]) -> bytes:
    """Build a PDF; a None entry becomes an image-only page with no text layer."""
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text is None:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50), False)
            pix.clear_with(200)
            page.insert_image(pymupdf.Rect(72, 72, 300, 300), pixmap=pix)
        else:
            page.insert_textbox(pymupdf.Rect(72, 72, 540, 770), text, fontsize=11)
    data = doc.tobytes(no_new_id=True)  # same text -> same bytes, so dedupe can be tested
    doc.close()
    return data

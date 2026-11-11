from backend.models.enums import ChunkKind
from backend.services.chunking import chunk_page, chunk_pages, count_tables


def test_chunks_keep_one_based_page_numbers_and_never_cross_pages():
    pages = [
        (1, "Alpha paragraph.\n\nBeta paragraph."),
        (2, "Gamma on page two."),
        (3, "Delta."),
    ]
    chunks = chunk_pages(pages, size=500, overlap=50)
    assert [c.page_number for c in chunks] == [1, 2, 3]
    assert "Gamma" in chunks[1].text and "Alpha" not in chunks[1].text


def test_long_text_is_split_with_overlap_on_same_page():
    text = " ".join(f"word{i}" for i in range(400))
    chunks = chunk_page(7, text, size=300, overlap=60)
    assert len(chunks) > 1
    assert all(c.page_number == 7 and len(c.text) <= 300 for c in chunks)
    assert (
        chunks[0].text.split()[-1] in chunks[1].text
    )  # overlap carries context forward


def test_tables_stay_whole_and_are_tagged():
    table = "| a | b |\n|---|---|\n" + "\n".join(f"| r{i} | v{i} |" for i in range(60))
    md = f"Intro text.\n\n{table}\n\nOutro text."
    chunks = chunk_page(3, md, size=200, overlap=20)
    tables = [c for c in chunks if c.kind is ChunkKind.TABLE]
    assert len(tables) == 1 and tables[0].text.count("\n") == 61
    assert count_tables(md) == 1


def test_empty_page_yields_no_chunks():
    assert chunk_page(1, "   \n\n ", size=200, overlap=20) == []

"""Page-aware chunking. Chunks never cross page boundaries; tables are kept whole."""

import re
from dataclasses import dataclass

from backend.models.enums import ChunkKind


@dataclass(frozen=True)
class TextChunk:
    page_number: int
    kind: ChunkKind
    text: str


_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")


def _blocks(markdown: str) -> list[tuple[ChunkKind, str]]:
    """Split page markdown into paragraphs, keeping consecutive table lines together."""
    blocks: list[tuple[ChunkKind, str]] = []
    para: list[str] = []
    table: list[str] = []

    def flush_para() -> None:
        if para:
            text = "\n".join(para).strip()
            if text:
                blocks.append((ChunkKind.TEXT, text))
            para.clear()

    def flush_table() -> None:
        if table:
            blocks.append((ChunkKind.TABLE, "\n".join(table).strip()))
            table.clear()

    for line in markdown.splitlines():
        if _TABLE_LINE.match(line):
            flush_para()
            table.append(line)
            continue
        flush_table()
        if line.strip():
            para.append(line)
        else:
            flush_para()
    flush_para()
    flush_table()
    return blocks


def count_tables(markdown: str) -> int:
    return sum(1 for kind, _ in _blocks(markdown) if kind is ChunkKind.TABLE)


def _split_long(text: str, size: int, overlap: int) -> list[str]:
    """Split oversized text on whitespace with character overlap."""
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = text.rfind(" ", start + size // 2, end)
            if cut != -1:
                end = cut
        pieces.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [p for p in pieces if p]


def chunk_page(page_number: int, markdown: str, *, size: int, overlap: int) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    buffer = ""

    def flush() -> None:
        nonlocal buffer
        if buffer.strip():
            chunks.append(TextChunk(page_number, ChunkKind.TEXT, buffer.strip()))
        buffer = ""

    for kind, block in _blocks(markdown):
        if kind is ChunkKind.TABLE:
            flush()
            # Tables stay whole even if longer than `size`, so rows keep their headers.
            chunks.append(TextChunk(page_number, ChunkKind.TABLE, block))
            continue
        if len(block) > size:
            flush()
            for piece in _split_long(block, size, overlap):
                chunks.append(TextChunk(page_number, ChunkKind.TEXT, piece))
            continue
        if buffer and len(buffer) + len(block) + 2 > size:
            tail = buffer[-overlap:] if overlap else ""
            flush()
            buffer = tail
        buffer = f"{buffer}\n\n{block}" if buffer else block
    flush()
    return chunks


def chunk_pages(pages: list[tuple[int, str]], *, size: int, overlap: int) -> list[TextChunk]:
    out: list[TextChunk] = []
    for page_number, markdown in pages:
        out.extend(chunk_page(page_number, markdown, size=size, overlap=overlap))
    return out

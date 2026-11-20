import json
import re
import uuid
from pathlib import PurePath

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session, selectinload

from backend.models import Document, DocumentChunk, Slide, SlideDeck
from backend.models.enums import DocumentStatus
from backend.rag.interfaces import ChatMessage, EmbeddingProvider, LLMProvider
from backend.rag.prompts import slides as slides_prompt
from backend.rag.prompts.common import format_sources, source_id
from backend.services.conversation_service import NotFoundError, get_conversation
from backend.services.retrieval import RetrievedChunk, retrieve
from backend.services.slides_export import cite

# Passages sent to the LLM: enough to cover a document, small enough for Groq's free tier.
MAX_PASSAGES = 16
# Extra requests when the model returns fewer slides than asked for.
TOP_UP_ATTEMPTS = 2
# A whole-deck revision may grow the deck, within the editor's limit.
MAX_REVISED_SLIDES = 20
TITLE_MAX = 120
BULLET_MAX = 300
MAX_BULLETS = 6
NOTES_MAX = 2000


class SlideGenerationError(Exception):
    """Safe to show to the student."""


def _spread_chunks(
    db: Session, owner_id: uuid.UUID, document_ids: list[uuid.UUID], limit: int
) -> list[RetrievedChunk]:
    """Evenly spaced passages in reading order, so a deck covers the whole document."""
    order = {doc_id: i for i, doc_id in enumerate(document_ids)}
    rows = db.execute(
        select(DocumentChunk.id, DocumentChunk.document_id, DocumentChunk.chunk_index)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.owner_id == owner_id,
            Document.status == DocumentStatus.COMPLETED,
            Document.id.in_(document_ids),
            func.length(DocumentChunk.text) > 150,
        )
    ).all()
    rows.sort(key=lambda r: (order.get(r.document_id, 0), r.chunk_index))
    if len(rows) > limit:
        step = (len(rows) - 1) / (limit - 1) if limit > 1 else 0
        rows = [rows[round(i * step)] for i in range(limit)]
    ids = [r.id for r in rows]
    if not ids:
        return []
    found = {
        c.id: (c, filename)
        for c, filename in db.execute(
            select(DocumentChunk, Document.filename)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.id.in_(ids))
        ).all()
    }
    return [
        RetrievedChunk(
            c.id, c.document_id, filename, c.page_number, c.kind, c.text, 1.0
        )
        for c, filename in (found[i] for i in ids if i in found)
    ]


# Passage ids like "(S2)", "[S3, S11]" or "S4:" that the model sometimes copies into text.
_SOURCE_REF = re.compile(r"\s*[(\[]\s*S\d+(?:\s*[,;]\s*S\d+)*\s*[)\]]|\bS\d+:\s*")


def _strip_refs(text: str) -> str:
    return " ".join(_SOURCE_REF.sub("", text).split())


def _clean(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = _strip_refs(value)
    return text if text and len(text) <= limit else None


def _ref_key(value: object) -> str:
    """Normalise a passage reference: "S3", "s3", "[S3]", "3" and 3 all mean S3."""
    key = str(value).strip().strip("[]()").strip().upper()
    return f"S{key}" if key.isdigit() else key


def _parse(
    raw: str,
    chunks: list[RetrievedChunk],
    count: int,
    *,
    require_sources: bool = True,
    skip_titles: set[str] | None = None,
) -> tuple[str | None, str | None, list[Slide]]:
    """Valid slides from a {"slides": [...]} response. `require_sources=False` keeps slides
    that cite nothing (revisions of the student's own text); `skip_titles` drops repeats."""
    try:
        data = json.loads(raw)
        items = data.get("slides")
    except (ValueError, AttributeError):
        data, items = None, None
    if not isinstance(items, list):
        raise SlideGenerationError(
            "The slide generator returned an invalid response. Please try again."
        )

    by_id = {source_id(i): c for i, c in enumerate(chunks)}
    slides: list[Slide] = []
    seen: set[str] = {t.lower() for t in (skip_titles or set())}
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _clean(item.get("title"), TITLE_MAX)
        raw_bullets = item.get("bullets")
        bullets = [
            b
            for b in (
                _clean(x, BULLET_MAX)
                for x in (raw_bullets if isinstance(raw_bullets, list) else [])
            )
            if b
        ][:MAX_BULLETS]
        refs = item.get("sources")
        keys = [_ref_key(s) for s in (refs if isinstance(refs, list) else [])]
        cited = [by_id[k] for k in keys if k in by_id]
        # Drop slides that are empty, untitled or (when required) not tied to a passage.
        if (
            not (title and bullets and (cited or not require_sources))
            or title.lower() in seen
        ):
            continue
        seen.add(title.lower())
        sources: list[dict] = []
        for c in cited:
            entry = {
                "document_id": str(c.document_id),
                "filename": c.filename,
                "page_number": c.page_number,
            }
            if entry not in sources:
                sources.append(entry)
        sources.sort(key=lambda s: (s["filename"], s["page_number"]))
        notes = item.get("notes")
        slides.append(
            Slide(
                position=len(slides) + 1,
                title=title,
                bullets=bullets,
                notes=_strip_refs(notes)[:NOTES_MAX] if isinstance(notes, str) else "",
                sources=sources,
            )
        )
        if len(slides) == count:
            break
    if not slides:
        raise SlideGenerationError(
            "No valid slides could be made from these PDFs. Try another topic."
        )
    return (
        _clean(data.get("title"), TITLE_MAX),
        _clean(data.get("subtitle"), 300),
        slides,
    )


def _merge_before_takeaways(slides: list[Slide], extra: list[Slide]) -> list[Slide]:
    """Add extra slides before a closing "Key takeaways" slide, then renumber."""
    tail = [slides.pop()] if slides and "takeaway" in slides[-1].title.lower() else []
    merged = slides + extra + tail
    for i, s in enumerate(merged, start=1):
        s.position = i
    return merged


def generate_deck(
    db: Session,
    *,
    owner_id: uuid.UUID,
    document_ids: list[uuid.UUID],
    conversation_id: uuid.UUID | None,
    topic: str | None,
    count: int,
    llm: LLMProvider,
    embedder: EmbeddingProvider,
) -> SlideDeck:
    if conversation_id is not None:
        conv = get_conversation(db, owner_id, conversation_id)
        if not document_ids:
            document_ids = [d.id for d in conv.documents]
    owned = db.scalars(
        select(Document).where(
            Document.owner_id == owner_id, Document.id.in_(document_ids)
        )
    ).all()
    if len(owned) != len(set(document_ids)):
        raise NotFoundError("One or more documents were not found.")
    ready_docs = {d.id for d in owned if d.status is DocumentStatus.COMPLETED}
    ready = [d for d in dict.fromkeys(document_ids) if d in ready_docs]
    if not ready:
        raise SlideGenerationError(
            "Select at least one processed PDF to make slides from."
        )

    topic = topic.strip() if topic and topic.strip() else None
    limit = min(count * 2, MAX_PASSAGES)
    if topic:
        chunks = retrieve(
            db,
            embedder,
            owner_id=owner_id,
            query=topic,
            document_ids=ready,
            top_k=limit,
        )
        # Present the passages in reading order so the deck follows the document.
        rank = {d: i for i, d in enumerate(ready)}
        chunks.sort(key=lambda c: (rank.get(c.document_id, 0), c.page_number))
    else:
        chunks = _spread_chunks(db, owner_id, ready, limit)
    if not chunks:
        raise SlideGenerationError(
            "These PDFs don't have enough text to make slides from."
        )

    sources_block = format_sources(chunks)
    result = llm.complete(
        [
            ChatMessage("system", slides_prompt.SYSTEM_PROMPT),
            ChatMessage("user", slides_prompt.user_turn(count, topic, sources_block)),
        ],
        json_mode=True,
    )
    title, subtitle, slides = _parse(result.text, chunks, count)

    # The model sometimes returns fewer slides than asked; ask for the rest, avoiding
    # the topics already covered.
    for _ in range(TOP_UP_ATTEMPTS):
        missing = count - len(slides)
        if missing <= 0:
            break
        titles = [s.title for s in slides]
        more = llm.complete(
            [
                ChatMessage("system", slides_prompt.SYSTEM_PROMPT),
                ChatMessage(
                    "user",
                    slides_prompt.more_turn(missing, topic, titles, sources_block),
                ),
            ],
            json_mode=True,
        )
        try:
            _, _, extra = _parse(more.text, chunks, missing, skip_titles=set(titles))
        except SlideGenerationError:
            break
        slides = _merge_before_takeaways(slides, extra)

    names = list(dict.fromkeys(c.filename for c in chunks))
    if not title:
        title = topic or PurePath(names[0]).stem
    deck = SlideDeck(
        owner_id=owner_id,
        conversation_id=conversation_id,
        title=title[:255],
        subtitle=(subtitle or "Based on " + ", ".join(names))[:500],
        topic=topic,
        slides=slides,
    )
    db.add(deck)
    db.commit()
    return deck


def list_decks(db: Session, owner_id: uuid.UUID) -> list[SlideDeck]:
    return list(
        db.scalars(
            select(SlideDeck)
            .where(SlideDeck.owner_id == owner_id)
            .options(selectinload(SlideDeck.slides))
            .order_by(SlideDeck.created_at.desc())
        )
    )


def get_deck(db: Session, owner_id: uuid.UUID, deck_id: uuid.UUID) -> SlideDeck:
    deck = db.scalar(
        select(SlideDeck)
        .where(SlideDeck.id == deck_id, SlideDeck.owner_id == owner_id)
        .options(selectinload(SlideDeck.slides))
    )
    if deck is None:
        raise NotFoundError("Slide deck not found.")
    return deck


def deck_filenames(deck: SlideDeck) -> list[str]:
    return list(
        dict.fromkeys(s["filename"] for slide in deck.slides for s in slide.sources)
    )


def update_deck(
    db: Session,
    deck: SlideDeck,
    *,
    title: str | None = None,
    subtitle: str | None = None,
    design: dict | None = None,
    clear_subtitle: bool = False,
) -> SlideDeck:
    if title is not None:
        deck.title = title.strip()[:255] or deck.title
    if subtitle is not None or clear_subtitle:
        deck.subtitle = (subtitle or "").strip()[:500] or None
    if design is not None:
        deck.design = design
    db.commit()
    return deck


def replace_slides(db: Session, deck: SlideDeck, edits: list) -> SlideDeck:
    """Apply the full edited slide list: existing slides keep their citations, new ones
    start without any, and slides left out are deleted."""
    existing = {s.id: s for s in deck.slides}
    used: set[uuid.UUID] = set()
    slides: list[Slide] = []
    for position, edit in enumerate(edits, start=1):
        slide = existing.get(edit.id) if edit.id not in used else None
        if slide is None:
            new_id = edit.id
            # A client id is only kept when it is unused everywhere (no clashes with other decks).
            if new_id is None or new_id in used or db.get(Slide, new_id) is not None:
                new_id = uuid.uuid4()
            slide = Slide(id=new_id, sources=[])
        used.add(slide.id)
        slide.position = position
        slide.title = edit.title[:255] or "Untitled slide"
        slide.bullets = list(edit.bullets)
        slide.notes = edit.notes
        if (
            edit.sources is not None
        ):  # restoring a snapshot (undo) brings citations back
            slide.sources = [s.model_dump(mode="json") for s in edit.sources]
        slides.append(slide)
    deck.slides = slides
    db.commit()
    db.refresh(deck)
    return deck


def _spread(items: list, limit: int) -> list:
    if len(items) <= limit:
        return items
    step = (len(items) - 1) / (limit - 1) if limit > 1 else 0
    return [items[round(i * step)] for i in range(limit)]


def _page_chunks(
    db: Session, owner_id: uuid.UUID, pages: list[tuple[uuid.UUID, int]], limit: int
) -> list[RetrievedChunk]:
    """Passages from the pages a deck already cites, in reading order."""
    if not pages:
        return []
    rows = db.execute(
        select(DocumentChunk, Document.filename)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.owner_id == owner_id,
            Document.status == DocumentStatus.COMPLETED,
            tuple_(DocumentChunk.document_id, DocumentChunk.page_number).in_(
                list(dict.fromkeys(pages))
            ),
        )
        .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
    ).all()
    return [
        RetrievedChunk(
            c.id, c.document_id, filename, c.page_number, c.kind, c.text, 1.0
        )
        for c, filename in _spread(rows, limit)
    ]


def _deck_documents(
    db: Session, owner_id: uuid.UUID, deck: SlideDeck
) -> list[uuid.UUID]:
    """Processed PDFs the deck was made from (via its citations or its chat)."""
    ids = {
        uuid.UUID(s["document_id"])
        for slide in deck.slides
        for s in slide.sources
        if s.get("document_id")
    }
    if deck.conversation_id is not None:
        try:
            conv = get_conversation(db, owner_id, deck.conversation_id)
            ids.update(d.id for d in conv.documents)
        except NotFoundError:
            pass
    if not ids:
        return []
    return list(
        db.scalars(
            select(Document.id).where(
                Document.owner_id == owner_id,
                Document.id.in_(ids),
                Document.status == DocumentStatus.COMPLETED,
            )
        )
    )


def _revision_sources(
    db: Session,
    embedder: EmbeddingProvider,
    owner_id: uuid.UUID,
    deck: SlideDeck,
    slides: list[Slide],
    instruction: str,
) -> list[RetrievedChunk]:
    """The cited pages of the slides being revised, plus passages that match the
    instruction (so "add an example about X" can draw on other parts of the PDF)."""
    pages = [
        (uuid.UUID(s["document_id"]), s["page_number"])
        for slide in slides
        for s in slide.sources
        if s.get("document_id")
    ]
    chunks = _page_chunks(db, owner_id, pages, 10 if len(slides) == 1 else 12)
    doc_ids = _deck_documents(db, owner_id, deck)
    if doc_ids:
        seen = {c.chunk_id for c in chunks}
        found = retrieve(
            db,
            embedder,
            owner_id=owner_id,
            query=instruction,
            document_ids=doc_ids,
            top_k=6,
        )
        chunks += [c for c in found if c.chunk_id not in seen]
    rank = {d: i for i, d in enumerate(dict.fromkeys(c.document_id for c in chunks))}
    chunks.sort(key=lambda c: (rank[c.document_id], c.page_number))
    return chunks[:MAX_PASSAGES]


def _slide_for_prompt(slide: Slide) -> dict:
    return {
        "title": slide.title,
        "bullets": slide.bullets,
        "notes": slide.notes,
        "cited_pages": cite(slide.sources) if slide.sources else "none",
    }


def revise_deck(
    db: Session,
    deck: SlideDeck,
    *,
    owner_id: uuid.UUID,
    instruction: str,
    slide_id: uuid.UUID | None,
    llm: LLMProvider,
    embedder: EmbeddingProvider,
) -> SlideDeck:
    """Rewrite one slide, or the whole deck, following the student's instruction."""
    instruction = " ".join(instruction.split())
    if slide_id is not None:
        target = next((s for s in deck.slides if s.id == slide_id), None)
        if target is None:
            raise NotFoundError("Slide not found.")
        chunks = _revision_sources(db, embedder, owner_id, deck, [target], instruction)
        result = llm.complete(
            [
                ChatMessage("system", slides_prompt.REVISE_SYSTEM_PROMPT),
                ChatMessage(
                    "user",
                    slides_prompt.revise_slide_turn(
                        format_sources(chunks),
                        _slide_for_prompt(target),
                        [s.title for s in deck.slides],
                        instruction,
                    ),
                ),
            ],
            json_mode=True,
        )
        _, _, revised = _parse(result.text, chunks, 1, require_sources=False)
        new = revised[0]
        target.title, target.bullets, target.notes = new.title, new.bullets, new.notes
        # New citations replace the old ones; a pure rewording keeps the slide's own.
        if new.sources:
            target.sources = new.sources
        db.commit()
        return deck

    chunks = _revision_sources(
        db, embedder, owner_id, deck, list(deck.slides), instruction
    )
    current = {
        "title": deck.title,
        "subtitle": deck.subtitle or "",
        "slides": [_slide_for_prompt(s) for s in deck.slides],
    }
    result = llm.complete(
        [
            ChatMessage("system", slides_prompt.REVISE_SYSTEM_PROMPT),
            ChatMessage(
                "user",
                slides_prompt.revise_deck_turn(
                    format_sources(chunks), current, instruction, MAX_REVISED_SLIDES
                ),
            ),
        ],
        json_mode=True,
    )
    title, subtitle, slides = _parse(
        result.text, chunks, MAX_REVISED_SLIDES, require_sources=False
    )
    # Slides that only reuse existing text keep the citations of the slide they came from.
    old_sources = {s.title.lower(): s.sources for s in deck.slides}
    for s in slides:
        if not s.sources:
            s.sources = list(old_sources.get(s.title.lower(), []))
    if title:
        deck.title = title[:255]
    if subtitle:
        deck.subtitle = subtitle[:500]
    deck.slides = slides
    db.commit()
    db.refresh(deck)
    return deck


def delete_deck(db: Session, deck: SlideDeck) -> None:
    db.delete(deck)
    db.commit()

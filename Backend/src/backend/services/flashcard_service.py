import json
import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from backend.database.base import utcnow
from backend.models import Document, Flashcard, FlashcardDeck
from backend.models.enums import DocumentStatus
from backend.rag.interfaces import ChatMessage, EmbeddingProvider, LLMProvider
from backend.rag.prompts import flashcards as flashcard_prompt
from backend.rag.prompts.common import format_sources, source_id
from backend.services.conversation_service import NotFoundError, get_conversation
from backend.services.quiz_service import _sample_chunks
from backend.services.retrieval import RetrievedChunk, retrieve

FRONT_MAX = 300
BACK_MAX = 1200


class FlashcardGenerationError(Exception):
    """Safe to show to the student."""


def _parse(raw: str, chunks: list[RetrievedChunk], count: int) -> list[Flashcard]:
    try:
        items = json.loads(raw).get("cards")
    except (ValueError, AttributeError):
        items = None
    if not isinstance(items, list):
        raise FlashcardGenerationError(
            "The flashcard generator returned an invalid response. Please try again."
        )

    by_id = {source_id(i): c for i, c in enumerate(chunks)}
    seen: set[str] = set()
    cards: list[Flashcard] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        front = item.get("front")
        back = item.get("back")
        chunk = by_id.get(item.get("source"))
        # Drop anything malformed, oversized or not tied to a retrieved passage.
        if not (
            isinstance(front, str)
            and isinstance(back, str)
            and front.strip()
            and back.strip()
            and len(front.strip()) <= FRONT_MAX
            and len(back.strip()) <= BACK_MAX
            and chunk is not None
        ):
            continue
        key = " ".join(front.lower().split())
        if key in seen:
            continue
        seen.add(key)
        cards.append(
            Flashcard(
                position=len(cards) + 1,
                front=front.strip(),
                back=back.strip(),
                known=False,
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                filename=chunk.filename,
                page_number=chunk.page_number,
            )
        )
        if len(cards) == count:
            break
    if not cards:
        raise FlashcardGenerationError(
            "No valid flashcards could be made from these PDFs. Try another topic."
        )
    return cards


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
) -> FlashcardDeck:
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
    ready = [d.id for d in owned if d.status is DocumentStatus.COMPLETED]
    if not ready:
        raise FlashcardGenerationError(
            "Select at least one processed PDF to make flashcards from."
        )

    topic = topic.strip() if topic and topic.strip() else None
    limit = min(count * 2, 24)
    if topic:
        chunks = retrieve(
            db,
            embedder,
            owner_id=owner_id,
            query=topic,
            document_ids=ready,
            top_k=limit,
        )
    else:
        chunks = _sample_chunks(db, owner_id, ready, limit)
    if not chunks:
        raise FlashcardGenerationError(
            "These PDFs don't have enough text to make flashcards from."
        )

    result = llm.complete(
        [
            ChatMessage("system", flashcard_prompt.SYSTEM_PROMPT),
            ChatMessage(
                "user",
                flashcard_prompt.user_turn(count, topic, format_sources(chunks)),
            ),
        ],
        json_mode=True,
    )
    cards = _parse(result.text, chunks, count)

    names = sorted({c.filename for c in chunks})
    title = (
        topic if topic else names[0] + (f" +{len(names) - 1}" if len(names) > 1 else "")
    )
    deck = FlashcardDeck(
        owner_id=owner_id,
        conversation_id=conversation_id,
        title=f"Flashcards: {title}"[:255],
        topic=topic,
        cards=cards,
    )
    db.add(deck)
    db.commit()
    return deck


def list_decks(db: Session, owner_id: uuid.UUID) -> list[FlashcardDeck]:
    return list(
        db.scalars(
            select(FlashcardDeck)
            .where(FlashcardDeck.owner_id == owner_id)
            .options(selectinload(FlashcardDeck.cards))
            .order_by(FlashcardDeck.created_at.desc())
        )
    )


def get_deck(db: Session, owner_id: uuid.UUID, deck_id: uuid.UUID) -> FlashcardDeck:
    deck = db.scalar(
        select(FlashcardDeck)
        .where(FlashcardDeck.id == deck_id, FlashcardDeck.owner_id == owner_id)
        .options(selectinload(FlashcardDeck.cards))
    )
    if deck is None:
        raise NotFoundError("Flashcard deck not found.")
    return deck


def mark_card(
    db: Session, deck: FlashcardDeck, card_id: uuid.UUID, known: bool
) -> Flashcard:
    card = next((c for c in deck.cards if c.id == card_id), None)
    if card is None:
        raise NotFoundError("Flashcard not found.")
    card.known = known
    card.reviewed_at = utcnow()
    db.commit()
    return card


def reset_progress(db: Session, deck: FlashcardDeck) -> FlashcardDeck:
    db.execute(
        update(Flashcard)
        .where(Flashcard.deck_id == deck.id)
        .values(known=False, reviewed_at=None)
    )
    db.commit()
    db.refresh(deck)
    for card in deck.cards:
        db.refresh(card)
    return deck


def delete_deck(db: Session, deck: FlashcardDeck) -> None:
    db.delete(deck)
    db.commit()

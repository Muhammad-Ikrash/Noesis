import uuid

from fastapi import APIRouter, HTTPException, status

from backend.api.dependencies import LLM, CurrentUser, DbSession, Embedder
from backend.models import FlashcardDeck
from backend.rag.interfaces import ProviderError
from backend.schemas.flashcard import (
    CardUpdate,
    DeckCreate,
    DeckOut,
    DeckSummary,
    FlashcardOut,
)
from backend.services import flashcard_service
from backend.services.conversation_service import NotFoundError
from backend.services.flashcard_service import FlashcardGenerationError

router = APIRouter(prefix="/flashcards", tags=["flashcards"])


def _owned(db: DbSession, user: CurrentUser, deck_id: uuid.UUID) -> FlashcardDeck:
    try:
        return flashcard_service.get_deck(db, user.id, deck_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


def _out(deck: FlashcardDeck) -> DeckOut:
    return DeckOut(
        id=deck.id,
        title=deck.title,
        topic=deck.topic,
        conversation_id=deck.conversation_id,
        created_at=deck.created_at,
        cards=[FlashcardOut.model_validate(c) for c in deck.cards],
    )


@router.post("", response_model=DeckOut, status_code=status.HTTP_201_CREATED)
def create_deck(
    body: DeckCreate, db: DbSession, user: CurrentUser, llm: LLM, embedder: Embedder
) -> DeckOut:
    """Generate a flashcard deck from the given PDFs (or a chat's attached PDFs)."""
    if not body.document_ids and body.conversation_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Provide document_ids or conversation_id.",
        )
    try:
        deck = flashcard_service.generate_deck(
            db,
            owner_id=user.id,
            document_ids=body.document_ids,
            conversation_id=body.conversation_id,
            topic=body.topic,
            count=body.card_count,
            llm=llm,
            embedder=embedder,
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except FlashcardGenerationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return _out(deck)


@router.get("", response_model=list[DeckSummary])
def list_decks(db: DbSession, user: CurrentUser) -> list[DeckSummary]:
    return [
        DeckSummary(
            id=d.id,
            title=d.title,
            topic=d.topic,
            conversation_id=d.conversation_id,
            card_count=len(d.cards),
            known_count=sum(1 for c in d.cards if c.known),
            last_studied_at=max(
                (c.reviewed_at for c in d.cards if c.reviewed_at), default=None
            ),
            created_at=d.created_at,
        )
        for d in flashcard_service.list_decks(db, user.id)
    ]


@router.get("/{deck_id}", response_model=DeckOut)
def get_deck(deck_id: uuid.UUID, db: DbSession, user: CurrentUser) -> DeckOut:
    return _out(_owned(db, user, deck_id))


@router.delete("/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deck(deck_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    flashcard_service.delete_deck(db, _owned(db, user, deck_id))


@router.patch("/{deck_id}/cards/{card_id}", response_model=FlashcardOut)
def mark_card(
    deck_id: uuid.UUID,
    card_id: uuid.UUID,
    body: CardUpdate,
    db: DbSession,
    user: CurrentUser,
) -> FlashcardOut:
    """Record a review: known = "Got it", false = "Still learning"."""
    deck = _owned(db, user, deck_id)
    try:
        card = flashcard_service.mark_card(db, deck, card_id, body.known)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return FlashcardOut.model_validate(card)


@router.post("/{deck_id}/reset", response_model=DeckOut)
def reset_deck(deck_id: uuid.UUID, db: DbSession, user: CurrentUser) -> DeckOut:
    """Mark every card as still learning again."""
    return _out(flashcard_service.reset_progress(db, _owned(db, user, deck_id)))

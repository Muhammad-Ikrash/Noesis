import re
import uuid
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Response, status

from backend.api.dependencies import LLM, CurrentUser, DbSession, Embedder
from backend.models import SlideDeck
from backend.rag.interfaces import ProviderError
from backend.schemas.slides import (
    SlideDeckCreate,
    SlideDeckOut,
    SlideDeckSummary,
    SlideDeckUpdate,
    SlideDesign,
    SlideOut,
    SlideRevise,
    SlidesReplace,
)
from backend.services import slides_service
from backend.services.conversation_service import NotFoundError
from backend.services.slides_export import build_pptx
from backend.services.slides_service import SlideGenerationError

router = APIRouter(prefix="/slides", tags=["slides"])

PPTX_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _owned(db: DbSession, user: CurrentUser, deck_id: uuid.UUID) -> SlideDeck:
    try:
        return slides_service.get_deck(db, user.id, deck_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


def _out(deck: SlideDeck) -> SlideDeckOut:
    return SlideDeckOut(
        id=deck.id,
        title=deck.title,
        subtitle=deck.subtitle,
        topic=deck.topic,
        conversation_id=deck.conversation_id,
        created_at=deck.created_at,
        design=design_of(deck),
        slides=[SlideOut.model_validate(s) for s in deck.slides],
    )


def design_of(deck: SlideDeck) -> SlideDesign:
    """Stored design merged over the defaults; unknown or invalid keys fall back."""
    try:
        return SlideDesign.model_validate(deck.design or {})
    except ValueError:
        return SlideDesign()


@router.post("", response_model=SlideDeckOut, status_code=status.HTTP_201_CREATED)
def create_deck(
    body: SlideDeckCreate,
    db: DbSession,
    user: CurrentUser,
    llm: LLM,
    embedder: Embedder,
) -> SlideDeckOut:
    """Generate presentation slides from the given PDFs (or a chat's attached PDFs)."""
    if not body.document_ids and body.conversation_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Provide document_ids or conversation_id.",
        )
    try:
        deck = slides_service.generate_deck(
            db,
            owner_id=user.id,
            document_ids=body.document_ids,
            conversation_id=body.conversation_id,
            topic=body.topic,
            count=body.slide_count,
            llm=llm,
            embedder=embedder,
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except SlideGenerationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return _out(deck)


@router.get("", response_model=list[SlideDeckSummary])
def list_decks(db: DbSession, user: CurrentUser) -> list[SlideDeckSummary]:
    return [
        SlideDeckSummary(
            id=d.id,
            title=d.title,
            subtitle=d.subtitle,
            topic=d.topic,
            conversation_id=d.conversation_id,
            slide_count=len(d.slides),
            filenames=slides_service.deck_filenames(d),
            created_at=d.created_at,
        )
        for d in slides_service.list_decks(db, user.id)
    ]


@router.get("/{deck_id}", response_model=SlideDeckOut)
def get_deck(deck_id: uuid.UUID, db: DbSession, user: CurrentUser) -> SlideDeckOut:
    return _out(_owned(db, user, deck_id))


@router.get(
    "/{deck_id}/pptx",
    response_class=Response,
    responses={200: {"content": {PPTX_TYPE: {}}}},
)
def download_pptx(deck_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Response:
    """The deck as an editable PowerPoint file (title slide, content slides, speaker notes)."""
    deck = _owned(db, user, deck_id)
    stem = re.sub(r"[^\w\- ]+", "", deck.title).strip()[:80] or "slides"
    ascii_stem = stem.encode("ascii", "ignore").decode() or "slides"
    disposition = (
        f'attachment; filename="{ascii_stem}.pptx"; '
        f"filename*=UTF-8''{quote(stem)}.pptx"
    )
    return Response(
        build_pptx(deck, design_of(deck)),
        media_type=PPTX_TYPE,
        headers={"Content-Disposition": disposition},
    )


@router.patch("/{deck_id}", response_model=SlideDeckOut)
def update_deck(
    deck_id: uuid.UUID, body: SlideDeckUpdate, db: DbSession, user: CurrentUser
) -> SlideDeckOut:
    """Rename the deck, change its subtitle, or save its design settings."""
    deck = _owned(db, user, deck_id)
    slides_service.update_deck(
        db,
        deck,
        title=body.title,
        subtitle=body.subtitle,
        clear_subtitle="subtitle" in body.model_fields_set and body.subtitle is None,
        design=body.design.model_dump() if body.design else None,
    )
    return _out(deck)


@router.put("/{deck_id}/slides", response_model=SlideDeckOut)
def replace_slides(
    deck_id: uuid.UUID, body: SlidesReplace, db: DbSession, user: CurrentUser
) -> SlideDeckOut:
    """Save edited slides: new order, edited text, added and removed slides."""
    deck = _owned(db, user, deck_id)
    return _out(slides_service.replace_slides(db, deck, body.slides))


@router.post("/{deck_id}/revise", response_model=SlideDeckOut)
def revise_deck(
    deck_id: uuid.UUID,
    body: SlideRevise,
    db: DbSession,
    user: CurrentUser,
    llm: LLM,
    embedder: Embedder,
) -> SlideDeckOut:
    """Ask the AI to change one slide, or the whole deck, as described in `instruction`."""
    deck = _owned(db, user, deck_id)
    try:
        deck = slides_service.revise_deck(
            db,
            deck,
            owner_id=user.id,
            instruction=body.instruction,
            slide_id=body.slide_id,
            llm=llm,
            embedder=embedder,
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except SlideGenerationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return _out(deck)


@router.delete("/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deck(deck_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    slides_service.delete_deck(db, _owned(db, user, deck_id))

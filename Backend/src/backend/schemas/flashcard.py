import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DeckCreate(BaseModel):
    # Either explicit documents, or a conversation whose attached PDFs are used.
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    conversation_id: uuid.UUID | None = None
    topic: str | None = Field(default=None, max_length=500)
    card_count: int = Field(default=12, ge=1, le=30)


class FlashcardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    front: str
    back: str
    known: bool
    reviewed_at: datetime | None
    document_id: uuid.UUID | None
    filename: str
    page_number: int


class DeckSummary(BaseModel):
    id: uuid.UUID
    title: str
    topic: str | None
    conversation_id: uuid.UUID | None
    card_count: int
    known_count: int
    last_studied_at: datetime | None
    created_at: datetime


class DeckOut(BaseModel):
    id: uuid.UUID
    title: str
    topic: str | None
    conversation_id: uuid.UUID | None
    created_at: datetime
    cards: list[FlashcardOut]


class CardUpdate(BaseModel):
    known: bool

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Theme = Literal["auto", "paper", "ink", "slate", "forest", "midnight"]
FontChoice = Literal["serif", "sans", "mono"]


class SlideDesign(BaseModel):
    """How a deck looks, in the app and in the PowerPoint export."""

    model_config = ConfigDict(extra="forbid")

    # "auto" follows the app's light/dark theme on screen and uses "paper" in PowerPoint.
    theme: Theme = "auto"
    # Overrides the theme's accent colour (rules, bullets, labels).
    accent: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    heading_font: FontChoice = "serif"
    body_font: FontChoice = "sans"
    align: Literal["left", "center"] = "left"
    bullets: Literal["dot", "dash", "number", "none"] = "dot"
    show_numbers: bool = True
    show_sources: bool = True


class SlideDeckCreate(BaseModel):
    # Either explicit documents, or a conversation whose attached PDFs are used.
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    conversation_id: uuid.UUID | None = None
    topic: str | None = Field(default=None, max_length=500)
    slide_count: int = Field(default=8, ge=3, le=15)


class SlideSource(BaseModel):
    document_id: uuid.UUID | None
    filename: str
    page_number: int


class SlideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    title: str
    bullets: list[str]
    notes: str
    sources: list[SlideSource]


class SlideDeckSummary(BaseModel):
    id: uuid.UUID
    title: str
    subtitle: str | None
    topic: str | None
    conversation_id: uuid.UUID | None
    slide_count: int
    filenames: list[str]
    created_at: datetime


class SlideDeckOut(BaseModel):
    id: uuid.UUID
    title: str
    subtitle: str | None
    topic: str | None
    conversation_id: uuid.UUID | None
    created_at: datetime
    design: SlideDesign
    slides: list[SlideOut]


class SlideDeckUpdate(BaseModel):
    """Fields left out are unchanged."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    subtitle: str | None = Field(default=None, max_length=500)
    design: SlideDesign | None = None


class SlideEdit(BaseModel):
    # Existing slides keep their id (and citations); new slides send a fresh id or none.
    id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=255)
    bullets: list[str] = Field(default_factory=list, max_length=10)
    notes: str = Field(default="", max_length=4000)
    # Only sent when restoring a snapshot (undo); otherwise citations are kept as they are.
    sources: list[SlideSource] | None = Field(default=None, max_length=50)

    @field_validator("title", "notes")
    @classmethod
    def _trim(cls, value: str) -> str:
        return value.strip()

    @field_validator("bullets")
    @classmethod
    def _bullets(cls, value: list[str]) -> list[str]:
        cleaned = [" ".join(b.split()) for b in value]
        if any(len(b) > 500 for b in cleaned):
            raise ValueError("Each bullet can be at most 500 characters.")
        return [b for b in cleaned if b]


class SlideRevise(BaseModel):
    """What to change, in the student's words; slide_id limits it to one slide."""

    instruction: str = Field(min_length=3, max_length=1000)
    slide_id: uuid.UUID | None = None


class SlidesReplace(BaseModel):
    """The deck's full slide list in its new order."""

    slides: list[SlideEdit] = Field(min_length=1, max_length=40)

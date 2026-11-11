"""Provider interfaces. Provider SDK code lives only in rag/providers/*."""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import pymupdf


@dataclass
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class LLMResult:
    text: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    model: str

    def complete(self, messages: list[ChatMessage], *, json_mode: bool = False) -> LLMResult: ...


class EmbeddingProvider(Protocol):
    model: str
    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class OCRProvider(Protocol):
    """Not implemented yet. Pages with too little text are flagged needs_ocr instead."""

    def extract_page_text(self, page: pymupdf.Page) -> str: ...


class ProviderError(Exception):
    """A provider call failed. The message is safe to show to clients."""

"""Prompt assembly and validation/normalisation of the model's structured answer."""

import json
import re
from dataclasses import dataclass, field

from backend.models.enums import AnswerStatus, LearningMode
from backend.rag.interfaces import ChatMessage
from backend.rag.prompts import system_prompt
from backend.rag.prompts.common import format_user_turn, source_id
from backend.services.retrieval import RetrievedChunk

_MARKER = re.compile(r"\[(S\d+)\]")
MAX_QUOTE_CHARS = 300

NO_SOURCES_BASIC = (
    "I couldn't find anything about this in the selected PDFs, so I can't answer it in basic mode. "
    "Would you like to upload or attach a PDF that covers this topic, or switch the search to your whole library?"
)
INVALID_RESPONSE = "The assistant returned an invalid response. Please try asking again."


@dataclass
class Citation:
    chunk: RetrievedChunk
    quote: str | None


@dataclass
class NormalizedAnswer:
    status: AnswerStatus
    answer: str
    supplementary: str | None = None
    clarification_question: str | None = None
    citations: list[Citation] = field(default_factory=list)

    @property
    def needs_clarification(self) -> bool:
        return self.status is AnswerStatus.NEEDS_CLARIFICATION


def build_messages(
    mode: LearningMode,
    history: list[ChatMessage],
    question: str,
    chunks: list[RetrievedChunk],
) -> list[ChatMessage]:
    return [
        ChatMessage("system", system_prompt(mode)),
        *history,
        ChatMessage("user", format_user_turn(question, chunks)),
    ]


def no_sources_answer() -> NormalizedAnswer:
    return NormalizedAnswer(AnswerStatus.INSUFFICIENT_CONTEXT, NO_SOURCES_BASIC)


def _str(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def normalize(raw: str, mode: LearningMode, chunks: list[RetrievedChunk]) -> NormalizedAnswer:
    """Validate the model's JSON. Citations pointing outside the retrieved context are dropped."""
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError
    except ValueError:
        return NormalizedAnswer(AnswerStatus.ERROR, INVALID_RESPONSE)

    try:
        status = AnswerStatus(data.get("answer_status"))
    except ValueError:
        status = AnswerStatus.ANSWERED
    if status is AnswerStatus.ERROR:
        status = AnswerStatus.ANSWERED

    answer = _str(data.get("answer")) or ""
    supplementary = _str(data.get("supplementary")) if mode is LearningMode.EXTENSIVE else None
    clarification = _str(data.get("clarification_question"))

    by_id = {source_id(i): c for i, c in enumerate(chunks)}
    quotes: dict[str, str | None] = {}
    raw_citations = data.get("citations") if isinstance(data.get("citations"), list) else []
    for item in raw_citations:
        if isinstance(item, dict) and item.get("source") in by_id:
            quotes.setdefault(item["source"], (_str(item.get("quote")) or "")[:MAX_QUOTE_CHARS] or None)
    for sid in _MARKER.findall(answer):
        if sid in by_id:
            quotes.setdefault(sid, None)

    # Number citations in first-appearance order and rewrite markers; unknown markers are removed.
    order = [sid for sid in dict.fromkeys(_MARKER.findall(answer)) if sid in quotes]
    order += [sid for sid in quotes if sid not in order]
    numbering = {sid: n + 1 for n, sid in enumerate(order)}
    answer = _MARKER.sub(lambda m: f"[{numbering[m.group(1)]}]" if m.group(1) in numbering else "", answer)
    citations = [Citation(by_id[sid], quotes[sid]) for sid in order]

    if status is AnswerStatus.NEEDS_CLARIFICATION and not clarification:
        status = AnswerStatus.ANSWERED if answer else AnswerStatus.INSUFFICIENT_CONTEXT
    if status is not AnswerStatus.NEEDS_CLARIFICATION:
        clarification = None

    if status is AnswerStatus.ANSWERED and not citations:
        if mode is LearningMode.BASIC:
            # Basic mode may not make uncited claims.
            return NormalizedAnswer(AnswerStatus.INSUFFICIENT_CONTEXT, NO_SOURCES_BASIC)
        # Extensive mode: uncited content must not be presented as coming from the PDF.
        supplementary = "\n\n".join(p for p in (answer, supplementary) if p) or None
        answer = "Your PDFs don't directly cover this, so everything below is additional explanation."
        status = AnswerStatus.INSUFFICIENT_CONTEXT

    if not answer and clarification:
        answer = clarification
    return NormalizedAnswer(status, answer, supplementary, clarification, citations)

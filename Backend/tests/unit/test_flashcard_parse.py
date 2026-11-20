import json
import uuid

import pytest

from backend.models.enums import ChunkKind
from backend.services.flashcard_service import FlashcardGenerationError, _parse
from backend.services.retrieval import RetrievedChunk

CHUNKS = [
    RetrievedChunk(
        uuid.uuid4(), uuid.uuid4(), "Bio.pdf", 5, ChunkKind.TEXT, "ATP...", 1.0
    )
]


def card(**kw):
    base = {
        "front": "Where is most ATP made?",
        "back": "In the mitochondria.",
        "source": "S1",
    }
    return base | kw


def test_valid_cards_keep_source_provenance():
    out = _parse(json.dumps({"cards": [card()]}), CHUNKS, 5)
    assert len(out) == 1
    c = out[0]
    assert (c.front, c.back, c.filename, c.page_number, c.position, c.known) == (
        "Where is most ATP made?",
        "In the mitochondria.",
        "Bio.pdf",
        5,
        1,
        False,
    )
    assert c.document_id == CHUNKS[0].document_id


@pytest.mark.parametrize(
    "bad",
    [
        {"source": "S9"},
        {"front": ""},
        {"back": "   "},
        {"front": 3},
        {"back": None},
        {"front": "x" * 301},
        {"back": "y" * 1201},
    ],
)
def test_malformed_or_unsourced_cards_are_dropped(bad):
    raw = json.dumps({"cards": [card(**bad), card(front="Second?")]})
    out = _parse(raw, CHUNKS, 5)
    assert [c.front for c in out] == ["Second?"]


def test_duplicates_are_dropped_and_count_is_capped():
    raw = json.dumps(
        {
            "cards": [
                card(),
                card(front="  where is most ATP   made? "),
                card(front="A?"),
                card(front="B?"),
            ]
        }
    )
    out = _parse(raw, CHUNKS, 2)
    assert [c.front for c in out] == ["Where is most ATP made?", "A?"]
    assert [c.position for c in out] == [1, 2]


@pytest.mark.parametrize("raw", ["not json", "[]", '{"cards": "x"}', '{"cards": []}'])
def test_unusable_response_is_a_clear_error(raw):
    with pytest.raises(FlashcardGenerationError):
        _parse(raw, CHUNKS, 5)

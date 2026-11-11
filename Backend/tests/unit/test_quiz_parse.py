import json
import uuid

import pytest

from backend.models.enums import ChunkKind
from backend.services.quiz_service import QuizGenerationError, _parse
from backend.services.retrieval import RetrievedChunk

CHUNKS = [
    RetrievedChunk(
        uuid.uuid4(), uuid.uuid4(), "Bio.pdf", 5, ChunkKind.TEXT, "ATP...", 1.0
    )
]


def q(**kw):
    base = {
        "question": "What makes ATP?",
        "options": ["Mitochondria", "Ribosome", "Nucleus", "Golgi"],
        "correct_index": 0,
        "explanation": "p5",
        "source": "S1",
    }
    return base | kw


def test_valid_questions_keep_source_provenance():
    out = _parse(json.dumps({"questions": [q()]}), CHUNKS, 5)
    assert (
        out[0].filename == "Bio.pdf"
        and out[0].page_number == 5
        and out[0].correct_index == 0
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"source": "S9"},
        {"options": ["a", "b", "c"]},
        {"correct_index": 4},
        {"correct_index": True},
        {"options": ["a", "a", "b", "c"]},
        {"question": " "},
    ],
)
def test_malformed_or_unsourced_questions_are_dropped(bad):
    out = _parse(
        json.dumps({"questions": [q(**bad), q(question="Second?")]}), CHUNKS, 5
    )
    assert [x.prompt for x in out] == ["Second?"]


def test_duplicates_dropped_and_count_capped():
    out = _parse(
        json.dumps({"questions": [q(), q(), q(question="B?"), q(question="C?")]}),
        CHUNKS,
        2,
    )
    assert [x.prompt for x in out] == ["What makes ATP?", "B?"]


def test_nothing_valid_raises():
    with pytest.raises(QuizGenerationError):
        _parse(json.dumps({"questions": [q(source="S2")]}), CHUNKS, 3)
    with pytest.raises(QuizGenerationError):
        _parse("nope", CHUNKS, 3)

import json
import uuid

import pytest

from backend.models import QuizQuestion
from backend.models.enums import ChunkKind, QuestionKind
from backend.services.quiz_service import QuizGenerationError, _parse, is_correct
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


# ---- Question types -----------------------------------------------------------


def tf(**kw):
    base = {
        "type": "true_false",
        "question": "ATP is made in the mitochondria.",
        "options": ["True", "False"],
        "correct_indices": [0],
        "explanation": "p5",
        "source": "S1",
    }
    return base | kw


def test_legacy_correct_index_becomes_single_choice():
    out = _parse(json.dumps({"questions": [q()]}), CHUNKS, 5)
    assert out[0].kind == "single" and out[0].correct_indices == [0]


def test_multiple_choice_keeps_every_correct_index():
    item = q(type="multiple", correct_indices=[2, 0], question="Which are organelles?")
    del item["correct_index"]
    out = _parse(json.dumps({"questions": [item]}), CHUNKS, 5)
    assert out[0].kind == "multiple"
    assert out[0].correct_indices == [0, 2] and out[0].correct_index == 0


@pytest.mark.parametrize("indexes", [[1], [0, 1, 2, 3], [0, 4]])
def test_multiple_choice_needs_two_or_three_valid_answers(indexes):
    bad = q(type="multiple", correct_indices=indexes)
    out = _parse(json.dumps({"questions": [bad, q(question="Fine?")]}), CHUNKS, 5)
    assert [x.prompt for x in out] == ["Fine?"]


def test_single_choice_rejects_several_answers():
    bad = q(correct_indices=[0, 1])
    del bad["correct_index"]
    out = _parse(json.dumps({"questions": [bad, q(question="Fine?")]}), CHUNKS, 5)
    assert [x.prompt for x in out] == ["Fine?"]


@pytest.mark.parametrize(
    ("options", "index", "expected"),
    [
        (["True", "False"], 0, 0),
        (["True", "False"], 1, 1),
        # Model put False first: still stored as True, False with the answer remapped.
        (["false", "TRUE"], 1, 0),
        (["False", "True"], 0, 1),
    ],
)
def test_true_false_is_normalised(options, index, expected):
    out = _parse(
        json.dumps({"questions": [tf(options=options, correct_indices=[index])]}),
        CHUNKS,
        5,
    )
    assert out[0].options == ["True", "False"]
    assert out[0].correct_indices == [expected]


@pytest.mark.parametrize(
    "options", [["Yes", "No"], ["True", "False", "Maybe"], ["True", "True"]]
)
def test_true_false_needs_true_and_false_options(options):
    out = _parse(
        json.dumps({"questions": [tf(options=options), q(question="Fine?")]}),
        CHUNKS,
        5,
    )
    assert [x.prompt for x in out] == ["Fine?"]


def test_types_the_student_did_not_ask_for_are_dropped():
    out = _parse(
        json.dumps({"questions": [tf(), q(), q(type="essay", question="Essay?")]}),
        CHUNKS,
        5,
        [QuestionKind.SINGLE],
    )
    assert [x.kind for x in out] == ["single"]


# ---- Grading --------------------------------------------------------------------


def _question(kind: str, correct: list[int], options: int = 4) -> QuizQuestion:
    return QuizQuestion(
        position=1,
        kind=kind,
        prompt="?",
        options=[str(i) for i in range(options)],
        correct_indices=correct,
        correct_index=correct[0],
    )


def test_single_choice_grading():
    question = _question("single", [2])
    assert is_correct(question, 2) and is_correct(question, [2])
    assert not is_correct(question, 1) and not is_correct(question, None)


def test_multiple_choice_needs_exactly_the_correct_set():
    question = _question("multiple", [0, 3])
    assert is_correct(question, [3, 0])
    assert not is_correct(question, [0])  # missing one
    assert not is_correct(question, [0, 1, 3])  # one extra
    assert not is_correct(question, [])  # skipped


def test_true_false_grading():
    question = _question("true_false", [1], options=2)
    assert is_correct(question, 1) and not is_correct(question, 0)


@pytest.mark.parametrize(
    ("kind", "correct", "options", "answer"),
    [
        ("single", [0], 4, 4),
        ("single", [0], 4, [0, 1]),
        ("true_false", [0], 2, 2),
        ("multiple", [0, 1], 4, [0, 9]),
    ],
)
def test_answers_that_do_not_fit_the_question_are_rejected(
    kind, correct, options, answer
):
    with pytest.raises(ValueError):
        is_correct(_question(kind, correct, options), answer)

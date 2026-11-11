import json
import uuid

from backend.models.enums import AnswerStatus, ChunkKind, LearningMode
from backend.rag.interfaces import ChatMessage
from backend.rag.pipeline import build_messages, normalize
from backend.rag.prompts import system_prompt
from backend.services.retrieval import RetrievedChunk, build_retrieval_query


def _chunk(page: int, text: str = "text") -> RetrievedChunk:
    return RetrievedChunk(uuid.uuid4(), uuid.uuid4(), "Bio.pdf", page, ChunkKind.TEXT, text, 0.9)


def _raw(**kw) -> str:
    base = {
        "answer_status": "answered",
        "answer": "",
        "supplementary": None,
        "clarification_question": None,
        "citations": [],
    }
    return json.dumps(base | kw)


def test_invented_citations_are_dropped_and_markers_renumbered():
    chunks = [_chunk(3), _chunk(9)]
    out = normalize(
        _raw(
            answer="A [S2]. B [S7]. C [S1].",
            citations=[{"source": "S2", "quote": "x"}, {"source": "S7", "quote": "fake"}],
        ),
        LearningMode.BASIC,
        chunks,
    )
    assert out.answer == "A [1]. B . C [2]."
    assert [c.chunk.page_number for c in out.citations] == [9, 3]


def test_basic_mode_rejects_uncited_answers():
    out = normalize(_raw(answer="The sky is blue."), LearningMode.BASIC, [_chunk(1)])
    assert out.status is AnswerStatus.INSUFFICIENT_CONTEXT
    assert out.citations == [] and "upload" in out.answer.lower()


def test_basic_mode_never_returns_supplementary():
    out = normalize(_raw(answer="X [S1]", supplementary="extra"), LearningMode.BASIC, [_chunk(1)])
    assert out.supplementary is None


def test_extensive_mode_keeps_supplementary_separate():
    out = normalize(
        _raw(answer="PDF says X [S1].", supplementary="Background: Y."), LearningMode.EXTENSIVE, [_chunk(4)]
    )
    assert out.status is AnswerStatus.ANSWERED
    assert out.supplementary == "Background: Y." and out.citations[0].chunk.page_number == 4


def test_extensive_mode_moves_uncited_claims_out_of_pdf_section():
    out = normalize(_raw(answer="General fact.", supplementary="More."), LearningMode.EXTENSIVE, [_chunk(1)])
    assert "General fact." in out.supplementary and "General fact." not in out.answer
    assert out.status is AnswerStatus.INSUFFICIENT_CONTEXT


def test_clarification_is_structured():
    out = normalize(
        _raw(answer_status="needs_clarification", clarification_question="Which chapter?"),
        LearningMode.EXTENSIVE,
        [_chunk(1)],
    )
    assert out.needs_clarification and out.clarification_question == "Which chapter?"


def test_invalid_json_is_an_error():
    assert normalize("not json", LearningMode.BASIC, []).status is AnswerStatus.ERROR


def test_modes_have_distinct_prompts_and_security_rules():
    basic, ext = system_prompt(LearningMode.BASIC), system_prompt(LearningMode.EXTENSIVE)
    assert "ONLY the passages" in basic and "general knowledge" in ext
    assert all("untrusted" in p for p in (basic, ext))


def test_history_is_context_and_sources_only_in_last_turn():
    history = [ChatMessage("user", "What is ATP?"), ChatMessage("assistant", "Energy [1].")]
    msgs = build_messages(LearningMode.BASIC, history, "why?", [_chunk(2, "ATP stores energy")])
    assert [m.role for m in msgs] == ["system", "user", "assistant", "user"]
    assert "<source" in msgs[-1].content and "<source" not in msgs[1].content


def test_retrieval_query_folds_previous_questions():
    assert build_retrieval_query("why?", ["What is ATP?"]) == "What is ATP?\nwhy?"

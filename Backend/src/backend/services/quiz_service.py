import json
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.models import Document, DocumentChunk, Quiz, QuizAttempt, QuizQuestion
from backend.models.enums import DocumentStatus, QuestionKind, QuizDifficulty
from backend.rag.interfaces import ChatMessage, EmbeddingProvider, LLMProvider
from backend.rag.prompts import quiz as quiz_prompt
from backend.rag.prompts.common import format_sources, source_id
from backend.services.conversation_service import NotFoundError, get_conversation
from backend.services.retrieval import RetrievedChunk, retrieve


TRUE_FALSE_OPTIONS = ("True", "False")


class QuizGenerationError(Exception):
    """Safe to show to the student."""


def _sample_chunks(
    db: Session, owner_id: uuid.UUID, document_ids: list[uuid.UUID], limit: int
) -> list[RetrievedChunk]:
    """Random spread of passages when no topic is given."""
    rows = db.execute(
        select(DocumentChunk, Document.filename)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.owner_id == owner_id,
            Document.status == DocumentStatus.COMPLETED,
            Document.id.in_(document_ids),
            func.length(DocumentChunk.text) > 150,
        )
        .order_by(func.random())
        .limit(limit)
    ).all()
    return [
        RetrievedChunk(
            c.id, c.document_id, filename, c.page_number, c.kind, c.text, 1.0
        )
        for c, filename in rows
    ]


def _indexes(item: dict) -> list[int] | None:
    """correct_indices as a sorted list of unique ints; accepts the older correct_index too."""
    raw = item.get("correct_indices")
    if raw is None and "correct_index" in item:
        raw = [item.get("correct_index")]
    if not isinstance(raw, list) or not raw:
        return None
    if not all(isinstance(i, int) and not isinstance(i, bool) for i in raw):
        return None
    return sorted(set(raw))


def _validate(
    kind: QuestionKind, options: object, indexes: list[int] | None
) -> tuple[list[str], list[int]] | None:
    """Clean options and correct indexes for one question, or None if it is malformed."""
    if indexes is None or not isinstance(options, list):
        return None
    if not all(isinstance(o, str) and o.strip() for o in options):
        return None
    options = [o.strip() for o in options]

    if kind is QuestionKind.TRUE_FALSE:
        # Always shown as True, False in that order, whatever order the model used.
        lowered = [o.lower() for o in options]
        if sorted(lowered) != ["false", "true"] or len(indexes) != 1:
            return None
        if not 0 <= indexes[0] < 2:
            return None
        answer_is_true = lowered[indexes[0]] == "true"
        return list(TRUE_FALSE_OPTIONS), [0 if answer_is_true else 1]

    if len(options) != 4 or len({o.lower() for o in options}) != 4:
        return None
    if not all(0 <= i < 4 for i in indexes):
        return None
    if kind is QuestionKind.SINGLE and len(indexes) != 1:
        return None
    if kind is QuestionKind.MULTIPLE and not 2 <= len(indexes) <= 3:
        return None
    return options, indexes


def _parse(
    raw: str,
    chunks: list[RetrievedChunk],
    count: int,
    kinds: list[QuestionKind] | None = None,
) -> list[QuizQuestion]:
    try:
        items = json.loads(raw).get("questions")
    except (ValueError, AttributeError):
        items = None
    if not isinstance(items, list):
        raise QuizGenerationError(
            "The quiz generator returned an invalid response. Please try again."
        )

    allowed = set(kinds or QuestionKind)
    by_id = {source_id(i): c for i, c in enumerate(chunks)}
    seen: set[str] = set()
    questions: list[QuizQuestion] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            kind = QuestionKind(item.get("type") or QuestionKind.SINGLE)
        except (ValueError, TypeError):  # unknown or non-string type
            continue
        prompt = item.get("question")
        chunk = by_id.get(item.get("source"))
        # Drop anything malformed, of a type the student didn't ask for,
        # or not tied to a retrieved passage.
        if kind not in allowed or chunk is None:
            continue
        if not (isinstance(prompt, str) and prompt.strip()):
            continue
        cleaned = _validate(kind, item.get("options"), _indexes(item))
        if cleaned is None:
            continue
        options, correct = cleaned
        key = prompt.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        questions.append(
            QuizQuestion(
                position=len(questions) + 1,
                kind=kind.value,
                prompt=prompt.strip(),
                options=options,
                correct_indices=correct,
                correct_index=correct[0],
                explanation=str(item.get("explanation") or "").strip(),
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                filename=chunk.filename,
                page_number=chunk.page_number,
            )
        )
        if len(questions) == count:
            break
    if not questions:
        raise QuizGenerationError(
            "No valid questions could be generated from these PDFs. Try another topic."
        )
    return questions


def generate_quiz(
    db: Session,
    *,
    owner_id: uuid.UUID,
    document_ids: list[uuid.UUID],
    conversation_id: uuid.UUID | None,
    topic: str | None,
    count: int,
    llm: LLMProvider,
    embedder: EmbeddingProvider,
    difficulty: QuizDifficulty = QuizDifficulty.MEDIUM,
    kinds: list[QuestionKind] | None = None,
) -> Quiz:
    kinds = list(dict.fromkeys(kinds or [QuestionKind.SINGLE]))
    if conversation_id is not None:
        conv = get_conversation(db, owner_id, conversation_id)
        if not document_ids:
            document_ids = [d.id for d in conv.documents]
    owned = db.scalars(
        select(Document).where(
            Document.owner_id == owner_id, Document.id.in_(document_ids)
        )
    ).all()
    if len(owned) != len(set(document_ids)):
        raise NotFoundError("One or more documents were not found.")
    ready = [d.id for d in owned if d.status is DocumentStatus.COMPLETED]
    if not ready:
        raise QuizGenerationError(
            "Select at least one processed PDF to build a quiz from."
        )

    topic = topic.strip() if topic and topic.strip() else None
    limit = min(count * 2, 24)
    if topic:
        chunks = retrieve(
            db,
            embedder,
            owner_id=owner_id,
            query=topic,
            document_ids=ready,
            top_k=limit,
        )
    else:
        chunks = _sample_chunks(db, owner_id, ready, limit)
    if not chunks:
        raise QuizGenerationError(
            "These PDFs don't have enough text to build a quiz from."
        )

    result = llm.complete(
        [
            ChatMessage("system", quiz_prompt.SYSTEM_PROMPT),
            ChatMessage(
                "user",
                quiz_prompt.user_turn(
                    count, topic, format_sources(chunks), difficulty, kinds
                ),
            ),
        ],
        json_mode=True,
    )
    questions = _parse(result.text, chunks, count, kinds)

    names = sorted({c.filename for c in chunks})
    title = (
        f"Quiz: {topic}"
        if topic
        else f"Quiz: {names[0]}" + (f" +{len(names) - 1}" if len(names) > 1 else "")
    )
    quiz = Quiz(
        owner_id=owner_id,
        conversation_id=conversation_id,
        title=title[:255],
        topic=topic,
        difficulty=difficulty.value,
        questions=questions,
    )
    db.add(quiz)
    db.commit()
    return quiz


def list_quizzes(db: Session, owner_id: uuid.UUID) -> list[Quiz]:
    return list(
        db.scalars(
            select(Quiz)
            .where(Quiz.owner_id == owner_id)
            .options(selectinload(Quiz.questions), selectinload(Quiz.attempts))
            .order_by(Quiz.created_at.desc())
        )
    )


def get_quiz(db: Session, owner_id: uuid.UUID, quiz_id: uuid.UUID) -> Quiz:
    quiz = db.scalar(
        select(Quiz)
        .where(Quiz.id == quiz_id, Quiz.owner_id == owner_id)
        .options(selectinload(Quiz.questions), selectinload(Quiz.attempts))
    )
    if quiz is None:
        raise NotFoundError("Quiz not found.")
    return quiz


def _chosen(question: QuizQuestion, answer: int | list[int] | None) -> set[int]:
    """The options picked for one question; raises ValueError if the answer doesn't fit it."""
    if answer is None:
        return set()
    picked = [answer] if isinstance(answer, int) else answer
    if any(isinstance(i, bool) or not 0 <= i < len(question.options) for i in picked):
        raise ValueError(
            f"Question {question.position}: answers must be option indexes "
            f"0-{len(question.options) - 1}."
        )
    if question.kind != QuestionKind.MULTIPLE and len(picked) > 1:
        raise ValueError(f"Question {question.position} takes a single answer.")
    return set(picked)


def is_correct(question: QuizQuestion, answer: int | list[int] | None) -> bool:
    """All correct options picked and nothing else; a skipped question is wrong."""
    chosen = _chosen(question, answer)
    return bool(chosen) and chosen == set(question.correct_indices)


def submit_attempt(
    db: Session, quiz: Quiz, answers: list[int | list[int] | None]
) -> QuizAttempt:
    if len(answers) != len(quiz.questions):
        raise ValueError(f"Expected {len(quiz.questions)} answers.")
    score = sum(
        1 for q, a in zip(quiz.questions, answers, strict=True) if is_correct(q, a)
    )
    attempt = QuizAttempt(
        quiz_id=quiz.id, answers=answers, score=score, total=len(answers)
    )
    db.add(attempt)
    db.commit()
    db.refresh(quiz)
    return attempt


def get_attempt(quiz: Quiz, attempt_id: uuid.UUID) -> QuizAttempt:
    for attempt in quiz.attempts:
        if attempt.id == attempt_id:
            return attempt
    raise NotFoundError("Attempt not found.")


RETRY_PREFIX = "Retry: "


def _safely_correct(question: QuizQuestion, answer: int | list[int] | None) -> bool:
    """is_correct for stored answers: one that no longer fits the question counts as missed."""
    try:
        return is_correct(question, answer)
    except ValueError:
        return False


def retry_missed(db: Session, quiz: Quiz, attempt: QuizAttempt) -> Quiz:
    """New quiz holding copies of the questions this attempt got wrong or skipped.

    It is an ordinary quiz, so it gets its own attempts and can be retried again.
    No model call is needed: the questions, answer keys and sources are copied as they are.
    """
    missed = [
        q
        for q, a in zip(quiz.questions, attempt.answers, strict=True)
        if not _safely_correct(q, a)
    ]
    if not missed:
        raise QuizGenerationError("Nothing to retry: every answer was correct.")

    # "Retry: Retry: X" reads badly, so a retry of a retry keeps a single prefix.
    base = quiz.title.removeprefix(RETRY_PREFIX)
    retry = Quiz(
        owner_id=quiz.owner_id,
        conversation_id=quiz.conversation_id,
        title=f"{RETRY_PREFIX}{base}"[:255],
        topic=quiz.topic,
        difficulty=quiz.difficulty,
        questions=[
            QuizQuestion(
                position=i + 1,
                kind=q.kind,
                prompt=q.prompt,
                options=list(q.options),
                correct_indices=list(q.correct_indices),
                correct_index=q.correct_index,
                explanation=q.explanation,
                chunk_id=q.chunk_id,
                document_id=q.document_id,
                filename=q.filename,
                page_number=q.page_number,
            )
            for i, q in enumerate(missed)
        ],
    )
    db.add(retry)
    db.commit()
    return retry


def delete_quiz(db: Session, quiz: Quiz) -> None:
    db.delete(quiz)
    db.commit()

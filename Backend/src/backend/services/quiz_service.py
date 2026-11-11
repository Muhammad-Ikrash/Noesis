import json
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.models import Document, DocumentChunk, Quiz, QuizAttempt, QuizQuestion
from backend.models.enums import DocumentStatus
from backend.rag.interfaces import ChatMessage, EmbeddingProvider, LLMProvider
from backend.rag.prompts import quiz as quiz_prompt
from backend.rag.prompts.common import format_sources, source_id
from backend.services.conversation_service import NotFoundError, get_conversation
from backend.services.retrieval import RetrievedChunk, retrieve


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


def _parse(raw: str, chunks: list[RetrievedChunk], count: int) -> list[QuizQuestion]:
    try:
        items = json.loads(raw).get("questions")
    except (ValueError, AttributeError):
        items = None
    if not isinstance(items, list):
        raise QuizGenerationError(
            "The quiz generator returned an invalid response. Please try again."
        )

    by_id = {source_id(i): c for i, c in enumerate(chunks)}
    seen: set[str] = set()
    questions: list[QuizQuestion] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        prompt = item.get("question")
        options = item.get("options")
        index = item.get("correct_index")
        chunk = by_id.get(item.get("source"))
        # Drop anything malformed or not tied to a retrieved passage.
        if not (
            isinstance(prompt, str)
            and prompt.strip()
            and chunk is not None
            and isinstance(options, list)
            and len(options) == 4
            and all(isinstance(o, str) and o.strip() for o in options)
            and len({o.strip().lower() for o in options}) == 4
            and isinstance(index, int)
            and not isinstance(index, bool)
            and 0 <= index < 4
        ):
            continue
        key = prompt.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        questions.append(
            QuizQuestion(
                position=len(questions) + 1,
                prompt=prompt.strip(),
                options=[o.strip() for o in options],
                correct_index=index,
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
) -> Quiz:
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
                "user", quiz_prompt.user_turn(count, topic, format_sources(chunks))
            ),
        ],
        json_mode=True,
    )
    questions = _parse(result.text, chunks, count)

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


def submit_attempt(db: Session, quiz: Quiz, answers: list[int | None]) -> QuizAttempt:
    if len(answers) != len(quiz.questions):
        raise ValueError(f"Expected {len(quiz.questions)} answers.")
    if any(a is not None and not 0 <= a < 4 for a in answers):
        raise ValueError("Answers must be option indexes 0-3 or null.")
    score = sum(
        1 for q, a in zip(quiz.questions, answers, strict=True) if a == q.correct_index
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


def delete_quiz(db: Session, quiz: Quiz) -> None:
    db.delete(quiz)
    db.commit()

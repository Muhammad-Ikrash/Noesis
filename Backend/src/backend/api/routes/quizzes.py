import uuid

from fastapi import APIRouter, HTTPException, status

from backend.api.dependencies import LLM, CurrentUser, DbSession, Embedder
from backend.models import Quiz, QuizAttempt
from backend.rag.interfaces import ProviderError
from backend.schemas.quiz import (
    AttemptCreate,
    AttemptResult,
    AttemptSummary,
    QuestionOut,
    QuestionReview,
    QuizCreate,
    QuizOut,
    QuizSummary,
)
from backend.services import quiz_service
from backend.services.conversation_service import NotFoundError
from backend.services.quiz_service import QuizGenerationError

router = APIRouter(prefix="/quizzes", tags=["quizzes"])


def _owned(db: DbSession, user: CurrentUser, quiz_id: uuid.UUID) -> Quiz:
    try:
        return quiz_service.get_quiz(db, user.id, quiz_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


def _out(quiz: Quiz) -> QuizOut:
    return QuizOut(
        id=quiz.id,
        title=quiz.title,
        topic=quiz.topic,
        conversation_id=quiz.conversation_id,
        created_at=quiz.created_at,
        questions=[QuestionOut.model_validate(q) for q in quiz.questions],
        attempts=[AttemptSummary.model_validate(a) for a in quiz.attempts],
    )


def _result(quiz: Quiz, attempt: QuizAttempt) -> AttemptResult:
    return AttemptResult(
        id=attempt.id,
        quiz_id=quiz.id,
        score=attempt.score,
        total=attempt.total,
        answers=attempt.answers,
        created_at=attempt.created_at,
        questions=[QuestionReview.model_validate(q) for q in quiz.questions],
    )


@router.post("", response_model=QuizOut, status_code=status.HTTP_201_CREATED)
def create_quiz(
    body: QuizCreate, db: DbSession, user: CurrentUser, llm: LLM, embedder: Embedder
) -> QuizOut:
    """Generate a multiple-choice quiz from the given PDFs (or a chat's attached PDFs)."""
    if not body.document_ids and body.conversation_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Provide document_ids or conversation_id.",
        )
    try:
        quiz = quiz_service.generate_quiz(
            db,
            owner_id=user.id,
            document_ids=body.document_ids,
            conversation_id=body.conversation_id,
            topic=body.topic,
            count=body.question_count,
            llm=llm,
            embedder=embedder,
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except QuizGenerationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return _out(quiz)


@router.get("", response_model=list[QuizSummary])
def list_quizzes(db: DbSession, user: CurrentUser) -> list[QuizSummary]:
    return [
        QuizSummary(
            id=q.id,
            title=q.title,
            topic=q.topic,
            conversation_id=q.conversation_id,
            question_count=len(q.questions),
            attempt_count=len(q.attempts),
            best_score=max((a.score for a in q.attempts), default=None),
            created_at=q.created_at,
        )
        for q in quiz_service.list_quizzes(db, user.id)
    ]


@router.get("/{quiz_id}", response_model=QuizOut)
def get_quiz(quiz_id: uuid.UUID, db: DbSession, user: CurrentUser) -> QuizOut:
    return _out(_owned(db, user, quiz_id))


@router.delete("/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quiz(quiz_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    quiz_service.delete_quiz(db, _owned(db, user, quiz_id))


@router.post(
    "/{quiz_id}/attempts",
    response_model=AttemptResult,
    status_code=status.HTTP_201_CREATED,
)
def submit_attempt(
    quiz_id: uuid.UUID, body: AttemptCreate, db: DbSession, user: CurrentUser
) -> AttemptResult:
    """Grade answers (option index per question, null = skipped) and reveal the answer key."""
    quiz = _owned(db, user, quiz_id)
    try:
        attempt = quiz_service.submit_attempt(db, quiz, body.answers)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return _result(quiz, attempt)


@router.get("/{quiz_id}/attempts/{attempt_id}", response_model=AttemptResult)
def get_attempt(
    quiz_id: uuid.UUID, attempt_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> AttemptResult:
    quiz = _owned(db, user, quiz_id)
    try:
        return _result(quiz, quiz_service.get_attempt(quiz, attempt_id))
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

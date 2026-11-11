import uuid

from fastapi import APIRouter, HTTPException, status

from backend.api.dependencies import LLM, AppSettings, CurrentUser, DbSession, Embedder
from backend.api.routes.conversations import owned_conversation
from backend.rag.interfaces import ProviderError
from backend.schemas.chat import AskRequest, AskResponse, RetrievedOut
from backend.schemas.conversation import MessageOut
from backend.services.answer_service import ask

router = APIRouter(prefix="/conversations", tags=["chat"])


@router.post("/{conversation_id}/messages", response_model=AskResponse)
def send_message(
    conversation_id: uuid.UUID,
    body: AskRequest,
    db: DbSession,
    user: CurrentUser,
    llm: LLM,
    embedder: Embedder,
    settings: AppSettings,
) -> AskResponse:
    conv = owned_conversation(db, user, conversation_id)
    try:
        result = ask(
            db,
            conversation=conv,
            question=body.question,
            mode=body.mode,
            scope=body.retrieval_scope,
            llm=llm,
            embedder=embedder,
            settings=settings,
        )
    except ProviderError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    assistant = MessageOut.model_validate(result.assistant_message)
    return AskResponse(
        conversation_id=conv.id,
        message_id=assistant.id,
        mode=assistant.mode,
        retrieval_scope=result.scope,
        answer_status=result.answer.status,
        answer=assistant.content,
        supplementary=assistant.supplementary,
        needs_clarification=assistant.needs_clarification,
        clarification_question=assistant.clarification_question,
        sources=assistant.sources,
        retrieved=[
            RetrievedOut(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                filename=c.filename,
                page_number=c.page_number,
                score=c.score,
            )
            for c in result.retrieved
        ],
        searched_document_count=result.searched_document_count,
        user_message=MessageOut.model_validate(result.user_message),
    )

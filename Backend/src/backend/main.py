import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.dependencies import get_ingestor, get_storage
from backend.api.routes import chat, conversations, documents, quizzes
from backend.api.routes import settings as settings_routes
from backend.core.config import get_settings
from backend.core.logging import configure_logging
from backend.database.session import get_sessionmaker
from backend.rag.factory import build_embedder, build_llm
from backend.services.document_service import mark_missing_files
from backend.services.ingestion import pending_document_ids

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    # Fail fast on invalid provider configuration.
    build_llm(settings)
    build_embedder(settings)

    storage = get_storage(settings)
    with get_sessionmaker()() as db:
        mark_missing_files(db, storage)
        pending = pending_document_ids(db)
    if pending:
        logger.info("Resuming ingestion for %d document(s)", len(pending))
        import threading

        ingest = get_ingestor(settings)
        threading.Thread(
            target=lambda: [ingest(i) for i in pending], daemon=True
        ).start()
    yield


def create_app(*, run_lifespan: bool = True) -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="0.1.0",
        lifespan=lifespan if run_lifespan else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            {"detail": "Internal server error."},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    @app.get("/api/v1/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for module in (documents, conversations, chat, quizzes, settings_routes):
        app.include_router(module.router, prefix="/api/v1")
    return app


app = create_app()

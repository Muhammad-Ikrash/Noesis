import uuid
from collections.abc import Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.config import Settings, get_settings
from backend.database.session import get_db, get_sessionmaker
from backend.models import User
from backend.rag.factory import get_embedder, get_llm
from backend.rag.interfaces import EmbeddingProvider, LLMProvider
from backend.services.ingestion import ingest_document
from backend.services.storage import FileStorage

# Authentication is out of scope for the local-only phase: every request acts as this user.
# Replace get_current_user with a token-based dependency when auth is added.
LOCAL_USER_EMAIL = "local@noesis.local"

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_current_user(db: DbSession) -> User:
    user = db.scalar(select(User).where(User.email == LOCAL_USER_EMAIL))
    if user is None:
        user = User(email=LOCAL_USER_EMAIL)
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            user = db.scalar(select(User).where(User.email == LOCAL_USER_EMAIL))
    return user


@lru_cache
def _storage(root: str) -> FileStorage:
    from pathlib import Path

    return FileStorage(Path(root))


def get_storage(settings: AppSettings) -> FileStorage:
    return _storage(str(settings.storage_dir))


Ingestor = Callable[[uuid.UUID], None]


def get_ingestor(settings: AppSettings) -> Ingestor:
    def run(document_id: uuid.UUID) -> None:
        ingest_document(
            document_id,
            session_factory=get_sessionmaker(),
            storage=get_storage(settings),
            embedder=get_embedder(),
            settings=settings,
        )

    return run


CurrentUser = Annotated[User, Depends(get_current_user)]
Storage = Annotated[FileStorage, Depends(get_storage)]
LLM = Annotated[LLMProvider, Depends(get_llm)]
Embedder = Annotated[EmbeddingProvider, Depends(get_embedder)]
IngestorDep = Annotated[Ingestor, Depends(get_ingestor)]

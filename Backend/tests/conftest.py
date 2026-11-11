import os
import uuid

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from backend.api import dependencies as deps
from backend.core.config import Settings, get_settings
from backend.database.session import get_db
from backend.main import create_app
from backend.models import User
from backend.rag.factory import get_embedder, get_llm
from backend.services.ingestion import ingest_document
from backend.services.storage import FileStorage
from tests.fakes import FakeEmbedder, FakeLLM

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://noesis:noesis@localhost:5432/noesis_test")
TABLES = (
    "message_sources, messages, conversation_documents, conversations, "
    "document_chunks, document_pages, documents, users"
)


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DATABASE_URL)
    try:
        with eng.connect():
            pass
    except Exception:
        pytest.skip(f"Postgres not reachable at TEST_DATABASE_URL ({TEST_DATABASE_URL}); run `docker compose up -d db`")
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.attributes["database_url"] = TEST_DATABASE_URL
    command.upgrade(cfg, "head")
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} CASCADE"))
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def db(session_factory):
    with session_factory() as s:
        yield s


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=TEST_DATABASE_URL,
        storage_dir=tmp_path / "uploads",
        llm_api_key="test",
        max_upload_mb=1,
        chunk_size=400,
        chunk_overlap=50,
        retrieval_top_k=4,
        history_max_messages=4,
    )


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def storage(settings) -> FileStorage:
    return FileStorage(settings.storage_dir)


@pytest.fixture
def client(session_factory, settings, embedder, llm, storage):
    app = create_app(run_lifespan=False)

    def _db():
        with session_factory() as s:
            yield s

    def _ingestor():
        # Runs synchronously inside the request's background task.
        return lambda doc_id: ingest_document(
            doc_id,
            session_factory=session_factory,
            storage=storage,
            embedder=embedder,
            settings=settings,
        )

    app.dependency_overrides.update(
        {
            get_db: _db,
            get_settings: lambda: settings,
            get_llm: lambda: llm,
            get_embedder: lambda: embedder,
            deps.get_storage: lambda: storage,
            deps.get_ingestor: _ingestor,
        }
    )
    with TestClient(app) as c:
        yield c


@pytest.fixture
def other_user(db) -> User:
    user = User(email=f"other-{uuid.uuid4().hex}@example.com")
    db.add(user)
    db.commit()
    return user

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProviderName(StrEnum):
    GROQ = "groq"


class EmbeddingProviderName(StrEnum):
    QWEN3 = "qwen3"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Noesis"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://noesis:noesis@localhost:5432/noesis"

    storage_dir: Path = Path("./data/uploads")
    max_upload_mb: int = Field(default=50, gt=0)

    llm_provider: LLMProviderName = LLMProviderName.GROQ
    llm_model: str = "llama-3.3-70b-versatile"
    llm_api_key: SecretStr | None = None
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_temperature: float = 0.2
    llm_timeout_seconds: float = 60.0

    embedding_provider: EmbeddingProviderName = EmbeddingProviderName.QWEN3
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    # Must match the pgvector column created by the migrations.
    embedding_dimension: int = 1024
    embedding_device: str = "auto"
    embedding_batch_size: int = Field(default=16, gt=0)

    chunk_size: int = Field(default=1800, gt=100)
    chunk_overlap: int = Field(default=200, ge=0)
    # Pages with fewer extracted characters than this are flagged as needing OCR.
    min_page_chars: int = 20

    retrieval_top_k: int = Field(default=8, gt=0, le=50)
    # Chunks with cosine similarity below this never reach the LLM. 0 disables the filter.
    retrieval_min_score: float = Field(default=0.3, ge=0, le=1)
    history_max_messages: int = Field(default=8, ge=0, le=50)
    # How many previous user turns are folded into the retrieval query.
    query_history_turns: int = Field(default=2, ge=0)

    cors_origins: list[str] = ["http://localhost:4200"]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @model_validator(mode="after")
    def _check(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        if self.embedding_device not in {"auto", "cuda", "cpu"}:
            raise ValueError("EMBEDDING_DEVICE must be one of: auto, cuda, cpu")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

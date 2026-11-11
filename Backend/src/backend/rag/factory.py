from functools import lru_cache

from backend.core.config import (
    EmbeddingProviderName,
    LLMProviderName,
    Settings,
    get_settings,
)
from backend.models import EMBEDDING_DIMENSION
from backend.rag.interfaces import EmbeddingProvider, LLMProvider


class ConfigurationError(Exception):
    pass


def build_llm(settings: Settings) -> LLMProvider:
    if settings.llm_provider is LLMProviderName.GROQ:
        from backend.rag.providers.llm.groq import GroqLLMProvider

        if settings.llm_api_key is None or not settings.llm_api_key.get_secret_value():
            raise ConfigurationError("LLM_API_KEY is required for the groq provider.")
        return GroqLLMProvider(
            api_key=settings.llm_api_key.get_secret_value(),
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_seconds,
        )
    raise ConfigurationError(f"Unsupported LLM provider: {settings.llm_provider}")


def build_embedder(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_dimension != EMBEDDING_DIMENSION:
        raise ConfigurationError(
            f"EMBEDDING_DIMENSION={settings.embedding_dimension} does not match the database "
            f"vector column ({EMBEDDING_DIMENSION}). Changing it requires a migration and re-embedding."
        )
    if settings.embedding_provider is EmbeddingProviderName.QWEN3:
        from backend.rag.providers.embeddings.qwen3 import Qwen3EmbeddingProvider

        return Qwen3EmbeddingProvider(
            model=settings.embedding_model,
            dimension=settings.embedding_dimension,
            device=settings.embedding_device,
            batch_size=settings.embedding_batch_size,
        )
    raise ConfigurationError(
        f"Unsupported embedding provider: {settings.embedding_provider}"
    )


@lru_cache
def get_llm() -> LLMProvider:
    return build_llm(get_settings())


@lru_cache
def get_embedder() -> EmbeddingProvider:
    return build_embedder(get_settings())

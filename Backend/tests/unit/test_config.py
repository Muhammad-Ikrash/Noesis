import pytest

from backend.core.config import Settings
from backend.rag.factory import ConfigurationError, build_embedder, build_llm


def test_embedding_dimension_must_match_database():
    with pytest.raises(ConfigurationError, match="does not match"):
        build_embedder(Settings(_env_file=None, embedding_dimension=768))


def test_missing_llm_key_is_a_clear_error():
    with pytest.raises(ConfigurationError, match="LLM_API_KEY"):
        build_llm(Settings(_env_file=None, llm_api_key=None))


def test_providers_are_configured_independently():
    s = Settings(_env_file=None, llm_api_key="k", llm_model="m1", embedding_model="e1")
    assert build_llm(s).model == "m1"
    assert build_embedder(s).model == "e1"


def test_overlap_must_be_smaller_than_chunk_size():
    with pytest.raises(ValueError):
        Settings(_env_file=None, chunk_size=200, chunk_overlap=200)

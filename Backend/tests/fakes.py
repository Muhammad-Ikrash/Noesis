"""Deterministic providers so tests never call paid APIs or download models."""

import hashlib
import json
import math
import re

from backend.rag.interfaces import ChatMessage, LLMResult

DIM = 1024
_WORD = re.compile(r"[a-z0-9]+")


def _vector(text: str, dim: int) -> list[float]:
    v = [0.0] * dim
    for word in _WORD.findall(text.lower()):
        v[int(hashlib.md5(word.encode()).hexdigest(), 16) % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


class FakeEmbedder:
    """Bag-of-words hashing: texts sharing words are close, so retrieval is meaningful."""

    def __init__(
        self, dimension: int = DIM, output_dimension: int | None = None
    ) -> None:
        self.model = "fake-embedder"
        self.dimension = dimension
        self._out = output_dimension or dimension
        self.queries: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [_vector(t, self._out) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return _vector(text, self._out)


class FakeLLM:
    """Returns queued responses; by default cites the first source."""

    def __init__(self) -> None:
        self.model = "fake-llm"
        self.calls: list[list[ChatMessage]] = []
        self.responses: list[str] = []

    def queue(self, **payload) -> None:
        self.responses.append(json.dumps(payload))

    def complete(
        self, messages: list[ChatMessage], *, json_mode: bool = False
    ) -> LLMResult:
        self.calls.append(messages)
        if self.responses:
            return LLMResult(self.responses.pop(0), self.model)
        return LLMResult(
            json.dumps(
                {
                    "answer_status": "answered",
                    "answer": "Grounded answer [S1].",
                    "supplementary": None,
                    "clarification_question": None,
                    "citations": [{"source": "S1", "quote": "q"}],
                }
            ),
            self.model,
        )

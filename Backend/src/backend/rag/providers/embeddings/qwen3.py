import logging
import math
import threading

from backend.rag.interfaces import ProviderError

logger = logging.getLogger(__name__)


class Qwen3EmbeddingProvider:
    """Local Qwen3-Embedding via sentence-transformers. Loaded lazily on first use."""

    def __init__(
        self, *, model: str, dimension: int, device: str, batch_size: int
    ) -> None:
        self.model = model
        self.dimension = dimension
        self._device = device
        self._batch_size = batch_size
        self._st = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._st is None:
                import torch
                from sentence_transformers import SentenceTransformer

                device = self._device
                if device == "auto":
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                logger.info("Loading embedding model %s on %s", self.model, device)
                # fp32: GTX 16-series cards have no tensor cores and fp16 can produce NaNs.
                self._st = SentenceTransformer(
                    self.model, device=device, truncate_dim=self.dimension
                )
            return self._st

    def _encode(self, texts: list[str], prompt_name: str | None) -> list[list[float]]:
        vectors = self._load().encode(
            texts,
            prompt_name=prompt_name,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        out = [v.tolist() for v in vectors]
        for v in out:
            if len(v) != self.dimension or not all(math.isfinite(x) for x in v):
                raise ProviderError("The embedding model returned an invalid vector.")
        return out

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts, None) if texts else []

    def embed_query(self, text: str) -> list[float]:
        # Qwen3 ships a "query" instruction prompt; documents are embedded without one.
        return self._encode([text], "query")[0]

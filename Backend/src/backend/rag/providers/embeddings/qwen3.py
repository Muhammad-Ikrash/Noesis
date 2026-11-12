import logging
import math
import threading

from backend.rag.interfaces import ProviderError

logger = logging.getLogger(__name__)


class Qwen3EmbeddingProvider:
    """Local Qwen3-Embedding via sentence-transformers. Loaded lazily on first use."""

    def __init__(
        self,
        *,
        model: str,
        dimension: int,
        device: str,
        batch_size: int,
        max_seq_length: int,
    ) -> None:
        self.model = model
        self.dimension = dimension
        self._device = device
        self._batch_size = batch_size
        self._max_seq_length = max_seq_length
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
                # Qwen3 defaults to 32k tokens; attention memory grows with the square of it.
                self._st.max_seq_length = self._max_seq_length
            return self._st

    def _encode(self, texts: list[str], prompt_name: str | None) -> list[list[float]]:
        import torch

        st = self._load()
        batch_size = self._batch_size
        while True:
            try:
                vectors = st.encode(
                    texts,
                    prompt_name=prompt_name,
                    batch_size=batch_size,
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                    show_progress_bar=False,
                )
                break
            except torch.OutOfMemoryError:
                torch.cuda.empty_cache()
                if batch_size == 1:
                    raise ProviderError("The embedding model ran out of GPU memory.")
                batch_size = max(1, batch_size // 2)
                logger.warning("CUDA OOM while embedding; retrying with batch size %d", batch_size)
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

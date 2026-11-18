import logging
import math
import os
import threading

from backend.rag.interfaces import ProviderError

logger = logging.getLogger(__name__)


def _cuda_usable() -> tuple[bool, str]:
    """torch.cuda.is_available() is True even when the installed PyTorch has no kernels
    for the GPU (e.g. an RTX 50-series card with a cu126 build), so run a tiny op to check."""
    import torch

    if not torch.cuda.is_available():
        return False, "no CUDA GPU detected"
    try:
        x = torch.ones(8, device="cuda")
        (x * 2).sum().item()
        return True, ""
    except RuntimeError as exc:  # torch.AcceleratorError subclasses RuntimeError
        first_line = (
            str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        )
        return False, first_line


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
        self._encode_batch_size = batch_size
        self._st = None
        self._lock = threading.Lock()

    def _resolve_device(self) -> str:
        import torch

        if self._device == "cpu":
            return "cpu"
        works, reason = _cuda_usable()
        if works:
            return "cuda"
        if self._device == "cuda":
            raise ProviderError(
                f"EMBEDDING_DEVICE=cuda, but the GPU can't be used ({reason}). "
                "Set EMBEDDING_DEVICE=cpu or install a PyTorch build that supports this GPU."
            )
        if torch.cuda.is_available():
            logger.warning(
                "GPU is not usable for embeddings (%s); using the CPU instead", reason
            )
        return "cpu"

    def _load(self):
        with self._lock:
            if self._st is None:
                import torch
                from sentence_transformers import SentenceTransformer

                device = self._resolve_device()
                if device == "cpu":
                    # Use every logical core; torch defaults to the physical ones only.
                    torch.set_num_threads(os.cpu_count() or torch.get_num_threads())
                    # One text per forward pass: chunks differ a lot in length, and on a CPU
                    # padding them to the longest in a batch costs more than batching saves.
                    self._encode_batch_size = 1
                else:
                    self._encode_batch_size = self._batch_size
                logger.info(
                    "Loading embedding model %s on %s (fp32, %d threads)",
                    self.model,
                    device,
                    torch.get_num_threads(),
                )
                # fp32 everywhere: the checkpoint is bf16, which is several times slower on
                # CPUs without bf16 support, and GTX 16-series GPUs can produce NaNs in fp16.
                self._st = SentenceTransformer(
                    self.model,
                    device=device,
                    truncate_dim=self.dimension,
                    model_kwargs={"dtype": torch.float32},
                )
                # Qwen3 defaults to 32k tokens; attention memory grows with the square of it.
                self._st.max_seq_length = self._max_seq_length
            return self._st

    def _encode(self, texts: list[str], prompt_name: str | None) -> list[list[float]]:
        import torch

        st = self._load()
        batch_size = self._encode_batch_size
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
                logger.warning(
                    "CUDA OOM while embedding; retrying with batch size %d", batch_size
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

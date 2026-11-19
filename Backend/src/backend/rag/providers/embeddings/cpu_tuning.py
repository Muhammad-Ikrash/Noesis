"""Pick the fastest CPU thread count for the embedding model by measuring it once per machine.

Guessing from the CPU model is unreliable (hybrid P/E-core CPUs can get slower with more
threads, SMT helps on some chips and not others), so a few short timed runs decide instead.
The result is cached in a small JSON file keyed by CPU, core count and PyTorch version.
"""

import json
import logging
import os
import platform
import time
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

# Fixed sample text, roughly one typical chunk, so timings are comparable between runs.
_SAMPLE = (
    "Cells convert nutrients into usable energy through cellular respiration. Glycolysis "
    "takes place in the cytoplasm and splits glucose into two molecules of pyruvate, "
    "producing a small amount of ATP and NADH. In the presence of oxygen, pyruvate enters "
    "the mitochondria, where the citric acid cycle releases carbon dioxide and transfers "
    "high-energy electrons to carriers. The electron transport chain then uses those "
    "electrons to pump protons across the inner membrane, and ATP synthase uses the "
    "resulting gradient to produce most of the cell's ATP. "
) * 3


def cpu_name() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine() or "unknown"


def thread_candidates(default: int, logical: int | None) -> list[int]:
    """Torch's default (usually the physical cores), every logical core, and half the
    default (close to the performance cores on hybrid CPUs)."""
    values = {default, max(1, default // 2)}
    if logical:
        values.add(logical)
    return sorted(values)


def calibration_key(torch_version: str, dtype: str) -> str:
    return f"{cpu_name()}|{os.cpu_count()}|torch {torch_version}|{dtype}"


def pick_fastest(
    candidates: list[int], measure: Callable[[int], float]
) -> tuple[int, dict[int, float]]:
    """Time each candidate and return the fastest one plus all timings (seconds)."""
    timings = {n: measure(n) for n in candidates}
    best = min(candidates, key=lambda n: (timings[n], n))
    return best, timings


def read_cached(path: Path | None, key: str) -> int | None:
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("key") != key:
        return None
    threads = data.get("threads")
    if not isinstance(threads, int) or isinstance(threads, bool) or threads < 1:
        return None
    return threads


def write_cached(
    path: Path | None, key: str, threads: int, timings: dict[int, float]
) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "key": key,
                    "threads": threads,
                    "seconds_per_text": {
                        str(n): round(t, 3) for n, t in timings.items()
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        logger.warning("Could not save the CPU calibration to %s", path)


def calibrate_threads(st, torch, cache_path: Path | None, dtype: str) -> int:
    """Set and return the fastest thread count for `st` (a loaded SentenceTransformer)."""
    key = calibration_key(torch.__version__, dtype)
    cached = read_cached(cache_path, key)
    if cached is not None:
        torch.set_num_threads(cached)
        logger.info("CPU calibration: using %d threads (cached)", cached)
        return cached

    candidates = thread_candidates(torch.get_num_threads(), os.cpu_count())
    if len(candidates) == 1:
        return candidates[0]

    logger.info("CPU calibration: timing %s threads, once per machine", candidates)
    st.encode([_SAMPLE], batch_size=1, show_progress_bar=False)  # first-run overhead

    def measure(n: int) -> float:
        torch.set_num_threads(n)
        st.encode(
            [_SAMPLE[:200]], batch_size=1, show_progress_bar=False
        )  # spin up pool
        start = time.perf_counter()
        st.encode([_SAMPLE, _SAMPLE], batch_size=1, show_progress_bar=False)
        return (time.perf_counter() - start) / 2

    best, timings = pick_fastest(candidates, measure)
    torch.set_num_threads(best)
    write_cached(cache_path, key, best, timings)
    logger.info(
        "CPU calibration: %d threads is fastest (%s)",
        best,
        ", ".join(f"{n} threads {t:.2f}s" for n, t in timings.items()),
    )
    return best

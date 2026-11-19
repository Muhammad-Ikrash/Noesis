import json

import pytest

from backend.core.config import Settings
from backend.rag.factory import build_embedder
from backend.rag.providers.embeddings import cpu_tuning
from backend.rag.providers.embeddings.cpu_tuning import (
    calibrate_threads,
    pick_fastest,
    read_cached,
    thread_candidates,
    write_cached,
)


def test_thread_candidates_cover_default_logical_and_half():
    assert thread_candidates(6, 12) == [3, 6, 12]
    assert thread_candidates(1, 1) == [1]
    assert thread_candidates(4, None) == [2, 4]


def test_pick_fastest_uses_measurements_and_breaks_ties_low():
    timings = {3: 1.2, 6: 0.9, 12: 0.65}
    assert pick_fastest([3, 6, 12], timings.__getitem__) == (12, timings)
    assert pick_fastest([4, 8], lambda n: 1.0)[0] == 4


def test_cache_round_trip_and_key_mismatch(tmp_path):
    path = tmp_path / "cal.json"
    write_cached(path, "cpu-a", 6, {6: 0.5, 12: 0.7})
    assert read_cached(path, "cpu-a") == 6
    assert read_cached(path, "cpu-b") is None  # new CPU or torch version: measure again


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[1, 2]",
        '{"key": "k", "threads": 0}',
        '{"key": "k", "threads": true}',
    ],
)
def test_bad_cache_is_ignored(tmp_path, content):
    path = tmp_path / "cal.json"
    path.write_text(content, encoding="utf-8")
    assert read_cached(path, "k") is None


def test_no_cache_path_is_fine():
    write_cached(None, "k", 4, {4: 1.0})
    assert read_cached(None, "k") is None


class FakeTorch:
    __version__ = "test"

    def __init__(self, default_threads):
        self.threads = default_threads
        self.set_calls = []

    def get_num_threads(self):
        return self.threads

    def set_num_threads(self, n):
        self.threads = n
        self.set_calls.append(n)


class FakeModel:
    """Encoding is fastest with 3 threads; time is simulated through a fake clock."""

    def __init__(self, torch, clock):
        self.torch, self.clock, self.calls = torch, clock, 0

    def encode(self, texts, **_):
        self.calls += 1
        self.clock[0] += {3: 0.4, 6: 0.6, 12: 0.9}.get(self.torch.threads, 1.0) * len(
            texts
        )


def _fake_env(monkeypatch, default=6, logical=12):
    clock = [0.0]
    monkeypatch.setattr(cpu_tuning.time, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(cpu_tuning.os, "cpu_count", lambda: logical)
    torch = FakeTorch(default)
    return torch, FakeModel(torch, clock)


def test_calibration_measures_once_then_uses_cache(tmp_path, monkeypatch):
    path = tmp_path / "cal.json"
    torch, st = _fake_env(monkeypatch)
    assert calibrate_threads(st, torch, path, "fp32") == 3
    assert torch.threads == 3
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["threads"] == 3 and set(saved["seconds_per_text"]) == {"3", "6", "12"}

    torch2, st2 = _fake_env(monkeypatch)
    assert calibrate_threads(st2, torch2, path, "fp32") == 3
    assert st2.calls == 0  # cached: no timing runs
    assert torch2.threads == 3


def test_calibration_is_redone_for_another_dtype(tmp_path, monkeypatch):
    path = tmp_path / "cal.json"
    torch, st = _fake_env(monkeypatch)
    calibrate_threads(st, torch, path, "fp32")
    torch2, st2 = _fake_env(monkeypatch)
    calibrate_threads(st2, torch2, path, "bf16")
    assert st2.calls > 0


def test_single_candidate_skips_timing(monkeypatch):
    torch, st = _fake_env(monkeypatch, default=1, logical=1)
    assert calibrate_threads(st, torch, None, "fp32") == 1
    assert st.calls == 0


def test_cpu_settings_are_validated_and_passed_through(tmp_path):
    with pytest.raises(ValueError, match="EMBEDDING_CPU_DTYPE"):
        Settings(_env_file=None, embedding_cpu_dtype="fp16")
    with pytest.raises(ValueError):
        Settings(_env_file=None, embedding_cpu_threads=-1)
    s = Settings(
        _env_file=None,
        embedding_cpu_dtype="bf16",
        embedding_cpu_threads=4,
        storage_dir=tmp_path / "uploads",
    )
    e = build_embedder(s)
    assert (e._cpu_dtype, e._cpu_threads) == ("bf16", 4)
    assert e._calibration_file == tmp_path / "embedding-cpu-calibration.json"

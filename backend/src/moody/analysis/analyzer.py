"""The analyzer interface, its result type, and a deterministic fake for tests and demos."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np
import numpy.typing as npt

from moody.legacy.thesis2007 import Features2007, classify_2007

TAG_THRESHOLD = 0.1
TOP_TAGS = 5


@dataclass(frozen=True)
class TrackAnalysis:
    valence: float  # [-1, 1]
    arousal: float  # [-1, 1]
    segments: tuple[tuple[float, float, float], ...]  # (start_s, valence, arousal)
    mood_probs: dict[str, float]
    tag_probs: dict[str, float]
    bpm: float | None = None
    key: str | None = None
    scale: str | None = None
    loudness_lufs: float | None = None
    features_2007: Features2007 | None = None
    embeddings: dict[str, npt.NDArray[np.float32]] = field(default_factory=dict)

    @property
    def top_tags(self) -> list[str]:
        ranked = sorted(self.tag_probs.items(), key=lambda kv: kv[1], reverse=True)
        return [tag for tag, p in ranked[:TOP_TAGS] if p >= TAG_THRESHOLD]

    @property
    def verdict_2007(self) -> tuple[str, str] | None:
        if self.features_2007 is None:
            return None
        octant, adjective = classify_2007(self.features_2007)
        return octant.label, adjective


class Analyzer(Protocol):
    def analyze(self, path: Path) -> TrackAnalysis: ...


class AnalysisError(RuntimeError):
    """A file could not be analyzed (too short, undecodable, ...)."""


class FakeAnalyzer:
    """Deterministic stand-in derived from the file's bytes. No audio decoding and no models."""

    def __init__(self, fail_on: frozenset[str] = frozenset(), embedding_dim: int = 8) -> None:
        self.fail_on = fail_on
        self.embedding_dim = embedding_dim

    def analyze(self, path: Path) -> TrackAnalysis:
        if path.name in self.fail_on:
            raise AnalysisError(f"fake failure for {path.name}")
        seed = int.from_bytes(hashlib.blake2b(path.read_bytes(), digest_size=8).digest(), "big")
        rng = np.random.default_rng(seed)
        v, a = (float(x) for x in rng.uniform(-1, 1, size=2))
        segments = tuple(
            (1.5 * i, float(np.clip(v + d1, -1, 1)), float(np.clip(a + d2, -1, 1)))
            for i, (d1, d2) in enumerate(rng.normal(0, 0.1, size=(4, 2)))
        )
        return TrackAnalysis(
            valence=v,
            arousal=a,
            segments=segments,
            mood_probs={"happy": (v + 1) / 2, "sad": (1 - v) / 2},
            tag_probs={"energetic": (a + 1) / 2, "calm": (1 - a) / 2},
            bpm=float(rng.uniform(60, 180)),
            key="C",
            scale="major",
            loudness_lufs=float(rng.uniform(-20, -6)),
            features_2007=Features2007(*(float(x) for x in rng.uniform(0, 100, size=5))),
            embeddings={
                "fake": rng.standard_normal(self.embedding_dim).astype(np.float32),
            },
        )

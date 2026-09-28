"""The 2007 Moody thesis model, ported to typed Python 3.

Source: ``DecisionTree.py``, ``Analyzer.py`` and ``Translators.py`` in
https://github.com/circuitflow/moody-2007 (commit 3b58348). The logic is reproduced
faithfully, including leaves that look odd today, so the 2007 system can serve as a
baseline in evaluation.

Five features, each normalized to 0-100, are thresholded into a 32-leaf tree. Every leaf
is a Hevner adjective assigned to one of the eight octants of Russell's circumplex.
"""

from __future__ import annotations

import csv
import math
from collections import Counter
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

import numpy as np
import numpy.typing as npt


class Octant(IntEnum):
    """Russell's circumplex octants, counter-clockwise from positive valence (0°)."""

    PLEASURE = 0
    EXCITEMENT = 1
    AROUSAL = 2
    DISTRESS = 3
    DISPLEASURE = 4
    DEPRESSION = 5
    SLEEPINESS = 6
    RELAXATION = 7

    @property
    def label(self) -> str:
        return self.name.capitalize()

    @property
    def angle_deg(self) -> float:
        return 45.0 * self.value

    @classmethod
    def from_label(cls, label: str) -> Octant:
        return cls[label.strip().upper()]


def octant_of(valence: float, arousal: float) -> Octant:
    """Octant containing a point in the valence/arousal plane (both in [-1, 1])."""
    angle = math.degrees(math.atan2(arousal, valence)) % 360.0
    return Octant(round(angle / 45.0) % 8)


def octant_center(octant: Octant, radius: float = 0.7) -> tuple[float, float]:
    """A representative (valence, arousal) point for an octant."""
    theta = math.radians(octant.angle_deg)
    return (radius * math.cos(theta), radius * math.sin(theta))


# Thresholds from DecisionTree.py; a feature at or above its threshold takes the first label.
THRESHOLDS: dict[str, tuple[float, str, str]] = {
    "mode": (50.0, "major", "minor"),
    "harmony": (75.0, "simple", "complex"),
    "tempo": (40.0, "fast", "slow"),
    "rhythm": (65.0, "regular", "irregular"),
    "loudness": (50.0, "loud", "soft"),
}
FEATURES: tuple[str, ...] = tuple(THRESHOLDS)

# (major, simple, fast, regular, loud) -> (octant, Hevner adjective)
HEVNER_TREE: dict[tuple[bool, bool, bool, bool, bool], tuple[Octant, str]] = {
    (True, True, True, True, True): (Octant.EXCITEMENT, "joyous"),
    (True, True, True, True, False): (Octant.RELAXATION, "graceful"),
    (True, True, True, False, True): (Octant.EXCITEMENT, "bright"),
    (True, True, True, False, False): (Octant.EXCITEMENT, "cheerful"),
    (True, True, False, True, True): (Octant.DEPRESSION, "solemn"),
    (True, True, False, True, False): (Octant.RELAXATION, "delicate"),
    (True, True, False, False, True): (Octant.EXCITEMENT, "happy"),
    (True, True, False, False, False): (Octant.RELAXATION, "serene"),
    (True, False, True, True, True): (Octant.AROUSAL, "triumphant"),
    (True, False, True, True, False): (Octant.DEPRESSION, "spiritual"),
    (True, False, True, False, True): (Octant.AROUSAL, "exciting"),
    (True, False, True, False, False): (Octant.DISTRESS, "restless"),
    (True, False, False, True, True): (Octant.DEPRESSION, "heavy"),
    (True, False, False, True, False): (Octant.DEPRESSION, "majestic"),
    (True, False, False, False, True): (Octant.DISTRESS, "angry"),
    (True, False, False, False, False): (Octant.DISTRESS, "tense"),
    (False, True, True, True, True): (Octant.AROUSAL, "sensational"),
    (False, True, True, True, False): (Octant.RELAXATION, "tender"),
    (False, True, True, False, True): (Octant.PLEASURE, "humorous"),
    (False, True, True, False, False): (Octant.PLEASURE, "playful"),
    (False, True, False, True, True): (Octant.DEPRESSION, "serious"),
    (False, True, False, True, False): (Octant.RELAXATION, "relaxed"),
    (False, True, False, False, True): (Octant.SLEEPINESS, "sentimental"),
    (False, True, False, False, False): (Octant.SLEEPINESS, "dreamy"),
    (False, False, True, True, True): (Octant.AROUSAL, "exhilarated"),
    (False, False, True, True, False): (Octant.AROUSAL, "soaring"),
    (False, False, True, False, True): (Octant.DEPRESSION, "vigorous"),
    (False, False, True, False, False): (Octant.DISTRESS, "agitated"),
    (False, False, False, True, True): (Octant.DISPLEASURE, "tragic"),
    (False, False, False, True, False): (Octant.DEPRESSION, "sad"),
    (False, False, False, False, True): (Octant.AROUSAL, "dramatic"),
    (False, False, False, False, False): (Octant.DISPLEASURE, "yearning"),
}


@dataclass(frozen=True)
class Features2007:
    """The thesis feature vector, each value on a 0-100 scale."""

    mode: float
    harmony: float
    tempo: float
    rhythm: float
    loudness: float

    def as_array(self) -> npt.NDArray[np.float64]:
        return np.array([self.mode, self.harmony, self.tempo, self.rhythm, self.loudness])


def classify_2007(features: Features2007) -> tuple[Octant, str]:
    """Run the thesis decision tree; returns (octant, Hevner adjective)."""

    def high(name: str) -> bool:
        return float(getattr(features, name)) >= THRESHOLDS[name][0]

    key = (high("mode"), high("harmony"), high("tempo"), high("rhythm"), high("loudness"))
    return HEVNER_TREE[key]


# Feature normalizations from Analyzer.py (inputs were Echo Nest analyzer values).


def normalize_tempo(bpm: float) -> float:
    """40-200 BPM -> 0-100."""
    return (bpm - 40.0) / 160.0 * 100.0


def normalize_loudness(loudness: float) -> float:
    """Echo Nest loudness 20-80 -> 0-100."""
    return (loudness - 20.0) / 60.0 * 100.0


def rhythm_regularity(
    tempo_confidence: float,
    beat_variance: float,
    tatum_confidence: float,
    time_signature_stability: float,
) -> float:
    """Weighted rhythm stability (beat variance weighs most), mapped 10-25 -> 0-100."""
    weighted = (
        30.0 * tempo_confidence
        + 50.0 * (1.0 - beat_variance)
        + 15.0 * tatum_confidence
        + 5.0 * time_signature_stability
    ) / 4.0
    return (weighted - 10.0) / 15.0 * 100.0


@dataclass(frozen=True)
class TrainingSong:
    title: str
    artist: str
    amg_mood: str
    octant: Octant
    hevner: str
    features: Features2007


def load_training(path: Path) -> list[TrainingSong]:
    """Load ``legacy/data/thesis2007_training.csv`` (written by ``legacy/convert.py``)."""
    with path.open(newline="") as f:
        return [
            TrainingSong(
                title=row["title"],
                artist=row["artist"],
                amg_mood=row["amg_mood"],
                octant=Octant.from_label(row["octant_2007"]),
                hevner=row["hevner_2007"],
                features=Features2007(*(float(row[name]) for name in FEATURES)),
            )
            for row in csv.DictReader(f)
        ]


def knn_2007(
    query: Features2007,
    train_x: npt.NDArray[np.float64],
    train_y: npt.NDArray[np.int_],
    k: int = 5,
) -> Octant:
    """The thesis k-NN: Euclidean distance, majority vote, ties go to the nearest neighbor."""
    dist = np.linalg.norm(train_x - query.as_array(), axis=1)
    nearest = np.argsort(dist, kind="stable")[:k]
    votes = Counter(int(train_y[i]) for i in nearest)
    top = max(votes.values())
    return Octant(next(int(train_y[i]) for i in nearest if votes[int(train_y[i])] == top))

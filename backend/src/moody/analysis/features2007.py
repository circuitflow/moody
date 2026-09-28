"""Re-derive the five 2007 thesis features from Essentia measurements.

The 2007 system read these from CLAM chord extraction and The Echo Nest analyzer, neither of
which exists any more. The mappings below are first approximations. The constants marked
CALIBRATE should be fitted in M4 against the original feature values of the 372-song thesis set
(``legacy/data/thesis2007_training.csv``), since those songs can be re-analyzed on the author's
machine.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from moody.legacy.thesis2007 import (
    Features2007,
    normalize_loudness,
    normalize_tempo,
    rhythm_regularity,
)

# RhythmExtractor2013(method="multifeature") confidence range, per the Essentia docs.
MULTIFEATURE_MAX_CONFIDENCE = 5.32
# CALIBRATE: Echo Nest loudness (as stored by the thesis) ~= integrated LUFS + offset.
# A track the thesis stored at 59.5 measures roughly -9 LUFS today.
ECHO_NEST_LOUDNESS_OFFSET = 68.5
# CALIBRATE: map mean ChordsDetection triad-fit strength onto the thesis's 0-100
# "harmonic simplicity" scale (CLAM measured the share of simple chord types).
CHORD_STRENGTH_RANGE = (0.3, 0.9)


@dataclass(frozen=True)
class RawMeasurements:
    """Audio measurements, as produced by ``EssentiaAnalyzer``."""

    chord_labels: tuple[str, ...]  # e.g. "C", "Am", from ChordsDetection
    chord_strengths: tuple[float, ...]
    bpm: float
    bpm_confidence: float
    beat_intervals: tuple[float, ...]  # seconds
    loudness_lufs: float


def _clip100(x: float) -> float:
    return float(np.clip(x, 0.0, 100.0))


def major_share(chords: tuple[str, ...]) -> float:
    """Share of major chords (0-100), the analogue of the thesis's weighted mode vote."""
    labelled = [c for c in chords if c and c != "N"]
    if not labelled:
        return 50.0
    return 100.0 * sum(1 for c in labelled if not c.endswith("m")) / len(labelled)


def harmonic_simplicity(strengths: tuple[float, ...]) -> float:
    lo, hi = CHORD_STRENGTH_RANGE
    if not strengths:
        return 50.0
    return _clip100((float(np.mean(strengths)) - lo) / (hi - lo) * 100.0)


def beat_variance(intervals: tuple[float, ...]) -> float:
    """Coefficient of variation of inter-beat intervals, clipped to [0, 1]."""
    x: npt.NDArray[np.float64] = np.asarray(intervals, dtype=np.float64)
    if len(x) < 2 or x.mean() <= 0:
        return 1.0
    return float(np.clip(x.std() / x.mean(), 0.0, 1.0))


def thesis_features(m: RawMeasurements) -> Features2007:
    confidence = float(np.clip(m.bpm_confidence / MULTIFEATURE_MAX_CONFIDENCE, 0.0, 1.0))
    return Features2007(
        mode=major_share(m.chord_labels),
        harmony=harmonic_simplicity(m.chord_strengths),
        tempo=_clip100(normalize_tempo(m.bpm)),
        # Essentia has no tatum or time-signature confidence: reuse the beat confidence and
        # assume a stable meter.
        rhythm=_clip100(
            rhythm_regularity(confidence, beat_variance(m.beat_intervals), confidence, 1.0)
        ),
        loudness=_clip100(normalize_loudness(m.loudness_lufs + ECHO_NEST_LOUDNESS_OFFSET)),
    )

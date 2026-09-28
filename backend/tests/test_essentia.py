"""Integration tests against real Essentia.

- DSP tests run wherever essentia-tensorflow is installed (``uv sync --extra analysis``).
- ``models`` tests also need the pretrained models (``moody models pull``) and are opt-in:
  ``pytest -m models``.
"""

import os
from pathlib import Path

import pytest

from tests.audio import write_clip

pytest.importorskip("essentia")

from moody.analysis.essentia_backend import EssentiaAnalyzer, dsp_measurements
from moody.analysis.features2007 import thesis_features
from moody.analysis.models import EFFNET, MUSICNN


@pytest.fixture(scope="module")
def clips(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("clips")
    return {kind: write_clip(root / f"{kind}.flac", kind) for kind in ("calm", "pulse", "noise")}


def test_dsp_on_pulse_clip(clips: dict[str, Path]) -> None:
    measurements, key, scale = dsp_measurements(clips["pulse"])
    assert measurements.bpm == pytest.approx(120, abs=3)
    assert (key, scale) in {("A", "minor"), ("C", "major")}  # A minor triad; relative major ok
    assert -30 < measurements.loudness_lufs < 0
    assert measurements.chord_labels


def test_dsp_features_2007_contrast(clips: dict[str, Path]) -> None:
    calm = thesis_features(dsp_measurements(clips["calm"])[0])
    pulse = thesis_features(dsp_measurements(clips["pulse"])[0])
    assert calm.loudness < pulse.loudness
    assert calm.mode > pulse.mode  # C major vs A minor


@pytest.fixture(scope="module")
def analyzer() -> EssentiaAnalyzer:
    models_dir = Path(os.environ.get("MOODY_MODELS_DIR", Path.home() / ".cache/moody/models"))
    return EssentiaAnalyzer(models_dir)


@pytest.mark.models
def test_full_analysis_shapes_and_ranges(
    analyzer: EssentiaAnalyzer, clips: dict[str, Path]
) -> None:
    result = analyzer.analyze(clips["pulse"])
    assert -1 <= result.valence <= 1 and -1 <= result.arousal <= 1
    assert len(result.segments) >= 10  # ~20 s at 1.5 s hop
    assert set(result.mood_probs) == {"happy", "sad", "aggressive", "relaxed", "party"}
    assert len(result.tag_probs) == 56
    assert all(0 <= p <= 1 for p in [*result.mood_probs.values(), *result.tag_probs.values()])
    assert result.embeddings[EFFNET].shape == (1280,)
    assert result.embeddings[MUSICNN].shape == (200,)
    assert result.verdict_2007 is not None


@pytest.mark.models
def test_calm_clip_is_lower_arousal_than_noise(
    analyzer: EssentiaAnalyzer, clips: dict[str, Path]
) -> None:
    assert analyzer.analyze(clips["calm"]).arousal < analyzer.analyze(clips["noise"]).arousal

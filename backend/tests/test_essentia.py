"""Integration tests against real Essentia.

- DSP tests run wherever essentia-tensorflow is installed (``uv sync --extra analysis``).
- ``models`` tests also need the pretrained models (``moody models pull``) and are opt-in:
  ``pytest -m models``.
"""

import os
from pathlib import Path

import pytest

from tests.audio import write_clip

if os.environ.get("MOODY_REQUIRE_ESSENTIA"):
    import essentia  # noqa: F401  - CI: fail loudly instead of skipping
else:
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


@pytest.mark.models
def test_no_tensorflow_startup_noise(tmp_path: Path, clips: dict[str, Path]) -> None:
    """A fresh process (like a scan worker) must not print TensorFlow's absl/MLIR notices."""
    import subprocess
    import sys

    models_dir = Path(os.environ.get("MOODY_MODELS_DIR", Path.home() / ".cache/moody/models"))
    env = {k: v for k, v in os.environ.items() if k != "TF_CPP_MIN_LOG_LEVEL"}
    code = (
        "from pathlib import Path; import sys\n"
        "from moody.analysis.essentia_backend import EssentiaAnalyzer\n"
        "EssentiaAnalyzer(Path(sys.argv[1])).analyze(Path(sys.argv[2]))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(models_dir), str(clips["calm"])],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    assert "mlir_graph_optimization" not in result.stderr
    assert "absl::InitializeLog" not in result.stderr


@pytest.mark.models
def test_wav_and_mp3_of_one_recording_count_as_duplicates(
    analyzer: EssentiaAnalyzer, tmp_path: Path
) -> None:
    """Calibrates moody.ingest.duplicates.MIN_SIMILARITY on the real EffNet embeddings."""
    import numpy as np

    from moody.ingest.duplicates import MIN_SIMILARITY

    def embedding(path: Path) -> np.ndarray:
        vec = analyzer.analyze(path).embeddings[EFFNET]
        return vec / np.linalg.norm(vec)

    wav = embedding(write_clip(tmp_path / "pulse.wav", "pulse"))
    mp3 = embedding(write_clip(tmp_path / "pulse.mp3", "pulse"))
    other = embedding(write_clip(tmp_path / "calm.wav", "calm"))
    same, different = float(wav @ mp3), float(wav @ other)
    print(f"cosine wav/mp3 {same:.4f}, different recordings {different:.4f}")
    assert same >= MIN_SIMILARITY
    assert different < MIN_SIMILARITY

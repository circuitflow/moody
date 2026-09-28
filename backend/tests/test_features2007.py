import pytest

from moody.analysis.features2007 import (
    RawMeasurements,
    beat_variance,
    harmonic_simplicity,
    major_share,
    thesis_features,
)


def raw(**overrides: object) -> RawMeasurements:
    base: dict[str, object] = {
        "chord_labels": ("C", "G", "Am", "F"),
        "chord_strengths": (0.8, 0.7, 0.9, 0.6),
        "bpm": 120.0,
        "bpm_confidence": 4.0,
        "beat_intervals": (0.5,) * 16,
        "loudness_lufs": -9.0,
    }
    base.update(overrides)
    return RawMeasurements(**base)  # type: ignore[arg-type]


def test_major_share() -> None:
    assert major_share(("C", "G", "Am", "F")) == 75
    assert major_share(("Am", "Em")) == 0
    assert major_share(()) == 50  # no evidence -> undecided


def test_harmonic_simplicity_is_clipped() -> None:
    assert harmonic_simplicity((1.0,)) == 100
    assert harmonic_simplicity((0.0,)) == 0


def test_beat_variance() -> None:
    assert beat_variance((0.5,) * 8) == 0
    assert beat_variance((0.5,)) == 1
    assert 0 < beat_variance((0.4, 0.6, 0.5, 0.45)) < 1


def test_thesis_features_are_on_0_100_scale() -> None:
    features = thesis_features(raw())
    assert features.mode == 75 and features.tempo == 50
    for value in vars(features).values():
        assert 0 <= value <= 100


def test_loudness_calibration_anchor() -> None:
    # 2Pac's "California Love" was stored at 65.9 by the thesis; it measures about -9 LUFS.
    assert thesis_features(raw(loudness_lufs=-9.0)).loudness == pytest.approx(65.8, abs=0.5)


def test_steady_confident_beat_is_regular() -> None:
    assert thesis_features(raw()).rhythm >= 65
    shaky = raw(bpm_confidence=0.5, beat_intervals=(0.3, 0.7, 0.4, 0.8, 0.35))
    assert thesis_features(shaky).rhythm < 65

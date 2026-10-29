import numpy as np
import pytest

from moody.evaluation import ccc, orientation_report, signal_correlations, verdict


@pytest.fixture
def annotations() -> tuple[np.ndarray, np.ndarray]:
    # Correlated valence/arousal, like real datasets (DEAM's are correlated too).
    rng = np.random.default_rng(0)
    shared = rng.normal(size=500)
    return shared + 0.6 * rng.normal(size=500), shared + 0.6 * rng.normal(size=500)


def noisy(x: np.ndarray, seed: int) -> np.ndarray:
    return x + 0.3 * np.random.default_rng(seed).normal(size=len(x))


def test_correct_orientation(annotations: tuple[np.ndarray, np.ndarray]) -> None:
    v, a = annotations
    report = orientation_report(np.column_stack([noisy(v, 1), noisy(a, 2)]), v, a)
    assert report["verdict"] == "as_labelled" and report["contrast_r"] > 0.5
    assert report["annotations_corr"] > 0.5  # the reason a plain r(col0, valence) is not enough


def test_swapped_orientation(annotations: tuple[np.ndarray, np.ndarray]) -> None:
    v, a = annotations
    report = orientation_report(np.column_stack([noisy(a, 1), noisy(v, 2)]), v, a)
    assert report["verdict"] == "swapped" and report["contrast_r"] < -0.5


def test_ccc_penalizes_offset_and_scale() -> None:
    x = np.linspace(-1, 1, 50)
    assert ccc(x, x) == pytest.approx(1.0)
    assert ccc(x + 1, x) < 0.5
    assert ccc(0.2 * x, x) < 0.5


def test_weak_contrast_is_undetermined() -> None:
    assert verdict(0.61) == "as_labelled"
    assert verdict(-0.5) == "swapped"
    assert verdict(-0.03) == "undetermined"
    assert verdict(0.19) == "undetermined"


def test_signal_correlations_isolates_what_separates_v_from_a() -> None:
    rng = np.random.default_rng(3)
    energy, loud = rng.normal(size=400), rng.normal(size=400)
    model_v = energy + 0.8 * loud  # valence leaning on loudness
    model_a = energy
    human_v = energy + 0.5 * rng.normal(size=400)  # listeners don't care about loudness
    human_a = energy + 0.5 * rng.normal(size=400)
    out = signal_correlations(model_v, model_a, {"loudness": loud}, human_v, human_a)["loudness"]
    assert out["model_v_minus_a"] > 0.9
    assert abs(out["human_v_minus_a"]) < 0.15 and abs(out["human_v"]) < 0.15
    assert set(signal_correlations(model_v, model_a, {"x": loud})["x"]) == {
        "model_v",
        "model_a",
        "model_v_minus_a",
    }

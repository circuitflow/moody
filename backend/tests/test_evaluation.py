import numpy as np
import pytest

from moody.evaluation import ccc, orientation_report


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

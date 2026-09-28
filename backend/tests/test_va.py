import numpy as np
import pytest

from moody.analysis import va


def test_normalize_maps_scale_endpoints() -> None:
    np.testing.assert_allclose(va.normalize([1, 5, 9]), [-1, 0, 1])
    np.testing.assert_allclose(va.normalize([0, 10]), [-1, 1])  # clipped


def test_normalize_is_monotone() -> None:
    x = np.sort(np.random.default_rng(1).uniform(0, 10, 200))
    assert np.all(np.diff(va.normalize(x)) >= 0)


@pytest.mark.parametrize("k", [1, 2, 3, 5])
def test_smooth_keeps_length_bounds_and_constants(k: int) -> None:
    x = np.random.default_rng(2).uniform(-1, 1, size=(17, 2))
    out = va.smooth(x, k)
    assert out.shape == x.shape
    assert out.min() >= x.min() - 1e-12 and out.max() <= x.max() + 1e-12
    np.testing.assert_allclose(va.smooth(np.full(9, 0.3), k), 0.3)


def test_smooth_short_series() -> None:
    np.testing.assert_allclose(va.smooth([0.5]), [0.5])

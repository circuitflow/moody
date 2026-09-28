"""Valence/arousal helpers."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]

# Essentia's DEAM/emoMusic heads regress onto the datasets' 1-9 rating scale.
RAW_MIN, RAW_MAX = 1.0, 9.0


def normalize(raw: npt.ArrayLike) -> FloatArray:
    """Map the 1-9 annotation scale linearly onto [-1, 1] (clipped)."""
    mid, half = (RAW_MIN + RAW_MAX) / 2, (RAW_MAX - RAW_MIN) / 2
    return np.clip((np.asarray(raw, dtype=np.float64) - mid) / half, -1.0, 1.0)


def smooth(series: npt.ArrayLike, k: int = 3) -> FloatArray:
    """Centered moving average along axis 0 with edge padding; keeps the length."""
    x = np.asarray(series, dtype=np.float64)
    if k <= 1 or len(x) < 2:
        return x.copy()
    pad = k // 2
    padded = np.pad(x, [(pad, k - 1 - pad)] + [(0, 0)] * (x.ndim - 1), mode="edge")
    kernel = np.ones(k) / k
    if x.ndim == 1:
        return np.convolve(padded, kernel, mode="valid")
    return np.stack(
        [np.convolve(padded[:, j], kernel, mode="valid") for j in range(x.shape[1])], axis=1
    )

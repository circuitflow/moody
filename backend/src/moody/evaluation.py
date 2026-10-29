"""Evaluation helpers for valence/arousal predictions against human annotations."""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]


def pearson(x: npt.ArrayLike, y: npt.ArrayLike) -> float:
    return float(
        np.corrcoef(np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64))[0, 1]
    )


def ccc(pred: npt.ArrayLike, truth: npt.ArrayLike) -> float:
    """Lin's concordance correlation coefficient (agreement in scale and offset, not just rank)."""
    p, t = np.asarray(pred, dtype=np.float64), np.asarray(truth, dtype=np.float64)
    cov = float(np.mean((p - p.mean()) * (t - t.mean())))
    return 2 * cov / float(p.var() + t.var() + (p.mean() - t.mean()) ** 2)


def orientation_report(
    pred: npt.ArrayLike, valence: npt.ArrayLike, arousal: npt.ArrayLike
) -> dict[str, Any]:
    """Check which output column of a 2-D valence/arousal model tracks which annotation.

    ``pred`` is ``[n, 2]`` in the column order the model's metadata declares
    (Essentia: ``[valence, arousal]``). Because valence and arousal are themselves correlated,
    the decisive number is ``contrast_r``: the correlation between the *difference* of the two
    output columns and the difference of the two annotations. It is positive when the columns
    are labelled correctly and negative when they are swapped.
    """
    p = np.asarray(pred, dtype=np.float64)
    v, a = np.asarray(valence, dtype=np.float64), np.asarray(arousal, dtype=np.float64)
    r = {
        "col0_vs_valence": pearson(p[:, 0], v),
        "col0_vs_arousal": pearson(p[:, 0], a),
        "col1_vs_valence": pearson(p[:, 1], v),
        "col1_vs_arousal": pearson(p[:, 1], a),
    }
    contrast = pearson(p[:, 0] - p[:, 1], v - a)
    return {
        "n": len(p),
        "pearson": r,
        "contrast_r": contrast,
        "ccc": {"col0_vs_valence": ccc(p[:, 0], v), "col1_vs_arousal": ccc(p[:, 1], a)},
        "outputs_corr": pearson(p[:, 0], p[:, 1]),
        "annotations_corr": pearson(v, a),
        "verdict": "as_labelled" if contrast > 0 else "swapped",
    }

"""Evaluation helpers for valence/arousal predictions against human annotations."""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]

# Below this |contrast_r| the two output columns carry no usable valence-vs-arousal signal,
# so neither "as labelled" nor "swapped" is a meaningful verdict.
UNDETERMINED_BELOW = 0.2


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
        "verdict": verdict(contrast),
    }


def verdict(contrast_r: float) -> str:
    if abs(contrast_r) < UNDETERMINED_BELOW:
        return "undetermined"
    return "as_labelled" if contrast_r > 0 else "swapped"


def signal_correlations(
    model_v: npt.ArrayLike,
    model_a: npt.ArrayLike,
    signals: dict[str, npt.ArrayLike],
    human_v: npt.ArrayLike | None = None,
    human_a: npt.ArrayLike | None = None,
) -> dict[str, dict[str, float]]:
    """Pearson r of each signal (mood probabilities, loudness, BPM, ...) with the model's
    valence, arousal and their difference, and with the human ratings when given.

    The ``*_v_minus_a`` columns show what separates valence from arousal: on a library where
    loudness tracks ``model_v_minus_a`` but not ``human_v_minus_a``, the model's valence is
    leaning on loudness rather than on what listeners call valence.
    """
    mv, ma = np.asarray(model_v, dtype=np.float64), np.asarray(model_a, dtype=np.float64)
    out: dict[str, dict[str, float]] = {}
    for name, raw in signals.items():
        x = np.asarray(raw, dtype=np.float64)
        row = {
            "model_v": pearson(mv, x),
            "model_a": pearson(ma, x),
            "model_v_minus_a": pearson(mv - ma, x),
        }
        if human_v is not None and human_a is not None:
            hv, ha = np.asarray(human_v, dtype=np.float64), np.asarray(human_a, dtype=np.float64)
            row |= {
                "human_v": pearson(hv, x),
                "human_a": pearson(ha, x),
                "human_v_minus_a": pearson(hv - ha, x),
            }
        out[name] = row
    return out


def roc_auc(scores: npt.ArrayLike, labels: npt.ArrayLike) -> float:
    """Area under the ROC curve: the chance a random positive outranks a random negative (ties
    count half). Mann-Whitney U with average ranks. NaN without both classes."""
    s = np.asarray(scores, dtype=np.float64)
    y = np.asarray(labels, dtype=bool)
    n_pos, n_neg = int(y.sum()), int((~y).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty(len(s), dtype=np.float64)
    sorted_s = s[order]
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and sorted_s[j + 1] == sorted_s[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2 + 1  # average rank for ties
        i = j + 1
    u = ranks[y].sum() - n_pos * (n_pos + 1) / 2
    return float(u / (n_pos * n_neg))


def average_precision(scores: npt.ArrayLike, labels: npt.ArrayLike) -> float:
    """Area under the precision-recall curve (step-wise, as in scikit-learn). Depends on how
    common the label is, so report it with its prevalence. NaN without positives."""
    s = np.asarray(scores, dtype=np.float64)
    y = np.asarray(labels, dtype=bool)
    if not y.any():
        return float("nan")
    order = np.argsort(-s, kind="mergesort")
    y_sorted = y[order]
    s_sorted = s[order]
    # Evaluate only at the last index of each run of equal scores (thresholds).
    last = np.r_[np.flatnonzero(np.diff(s_sorted)), len(s) - 1]
    tp = np.cumsum(y_sorted)[last]
    precision = tp / (last + 1)
    recall = tp / y.sum()
    prev_recall = np.r_[0.0, recall[:-1]]
    return float(np.sum((recall - prev_recall) * precision))

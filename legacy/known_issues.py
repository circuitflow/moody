"""Reproduce the numbers in legacy/README.md, "Known issues in the 2007 system".

Run from ``backend/``:  uv run python ../legacy/known_issues.py
Uses only the converted training set and the faithful port in ``moody.legacy.thesis2007``.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import numpy as np

from moody.legacy.thesis2007 import (
    FEATURES,
    HEVNER_TREE,
    THRESHOLDS,
    Features2007,
    Octant,
    classify_2007,
    knn_2007,
    load_training,
)

CSV = Path(__file__).parent / "data" / "thesis2007_training.csv"
NOISE_SD = (1.0, 3.0, 5.0)  # feature noise, in points on the 0-100 scale
NOISE_REPS = 200
LOW_AROUSAL = {Octant.DEPRESSION, Octant.SLEEPINESS, Octant.RELAXATION}


def main() -> None:
    songs = load_training(CSV)
    n = len(songs)
    x = np.stack([s.features.as_array() for s in songs])
    y = np.array([s.octant.value for s in songs])
    base = [classify_2007(s.features)[0] for s in songs]

    print(f"songs: {n}")

    # 1. Labels are the tree's own outputs.
    same = sum(classify_2007(s.features) == (s.octant, s.hevner) for s in songs)
    print(f"1. labels reproduced by the tree: {same}/{n}")
    knn = sum(
        knn_2007(s.features, x[np.arange(n) != i], y[np.arange(n) != i], k=5) == s.octant
        for i, s in enumerate(songs)
    )
    print(f"   k-NN (k=5) leave-one-out agreement with those labels: {knn}/{n} ({knn / n:.1%})")

    # 2. Thresholds at the medians, and sensitivity to measurement noise.
    print("2. feature | median | threshold | songs within +/-5 of threshold")
    for i, name in enumerate(FEATURES):
        threshold = THRESHOLDS[name][0]
        near = int(np.sum(np.abs(x[:, i] - threshold) < 5))
        print(
            f"   {name:<8} | {np.median(x[:, i]):5.1f} | {threshold:4.0f} | {near} ({near / n:.0%})"
        )
    rng = np.random.default_rng(0)
    for sd in NOISE_SD:
        changed = np.mean(
            [
                np.mean(
                    [
                        classify_2007(Features2007(*row))[0] != b
                        for row, b in zip(x + rng.normal(0, sd, x.shape), base, strict=True)
                    ]
                )
                for _ in range(NOISE_REPS)
            ]
        )
        print(f"   noise sd {sd:.0f} point(s): {changed:.0%} of songs change octant")

    # 3. Fast + loud leaves that land in a low-arousal octant.
    leaves = Counter(classify_2007(s.features) for s in songs)
    for key, (octant, adjective) in HEVNER_TREE.items():
        _major, _simple, fast, _regular, loud = key
        if fast and loud and octant in LOW_AROUSAL:
            count = leaves[(octant, adjective)]
            examples = [s.title for s in songs if classify_2007(s.features) == (octant, adjective)]
            print(
                f"3. fast+loud '{adjective}' -> {octant.label}: {count} songs, e.g. {examples[:3]}"
            )

    # 4. Minor-mode leaves that land in Pleasure.
    for key, (octant, adjective) in HEVNER_TREE.items():
        if not key[0] and octant is Octant.PLEASURE:
            print(f"4. minor '{adjective}' -> Pleasure: {leaves[(octant, adjective)]} songs")

    # 7. Lyric affect vs audio verdict.
    with CSV.open(newline="") as f:
        with_lyrics = [r for r in csv.DictReader(f) if r["lyrics_octant"]]
    agree = sum(r["lyrics_octant"] == r["octant_2007"] for r in with_lyrics)
    print(f"7. lyric octant == audio octant: {agree}/{len(with_lyrics)} (chance 1/8 = 12.5%)")


if __name__ == "__main__":
    main()

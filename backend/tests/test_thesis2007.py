import json
import math
from pathlib import Path

import numpy as np
import pytest

from moody.legacy.thesis2007 import (
    HEVNER_TREE,
    Features2007,
    Octant,
    classify_2007,
    knn_2007,
    load_training,
    normalize_loudness,
    normalize_tempo,
    octant_center,
    octant_of,
    rhythm_regularity,
)

FIXTURES = Path(__file__).parent / "fixtures"
TRAINING_CSV = Path(__file__).parents[2] / "legacy" / "data" / "thesis2007_training.csv"

# Expected outputs recorded by running the original 2007 DecisionTree.py under Python 3.
TREE_CASES = json.loads((FIXTURES / "thesis2007_tree.json").read_text())

# Leave-one-out k=5 accuracy of the thesis k-NN against the tree labels (241/372).
BASELINE_LOO_ACCURACY = 241 / 372


@pytest.mark.parametrize("case", TREE_CASES, ids=lambda c: c["adjective"])
def test_tree_matches_original(case: dict[str, object]) -> None:
    octant, adjective = classify_2007(Features2007(*case["features"]))
    assert (octant.value, adjective) == (case["octant"], case["adjective"])


def test_tree_has_32_leaves_covering_all_octants() -> None:
    assert len(HEVNER_TREE) == 32
    assert {octant for octant, _ in HEVNER_TREE.values()} == set(Octant)


@pytest.mark.parametrize("octant", list(Octant))
def test_octant_geometry_round_trips(octant: Octant) -> None:
    assert octant_of(*octant_center(octant)) == octant


def test_octant_axes() -> None:
    assert octant_of(1, 0) == Octant.PLEASURE
    assert octant_of(0, 1) == Octant.AROUSAL
    assert octant_of(-1, 0) == Octant.DISPLEASURE
    assert octant_of(0, -1) == Octant.SLEEPINESS
    assert Octant.from_label("Relaxation") is Octant.RELAXATION


def test_normalizations() -> None:
    assert normalize_tempo(40) == 0 and normalize_tempo(200) == 100
    assert normalize_loudness(20) == 0 and normalize_loudness(80) == 100
    # Perfectly stable rhythm: (30 + 50 + 15 + 5) / 4 = 25 -> 100
    assert math.isclose(rhythm_regularity(1, 0, 1, 1), 100)


def test_training_set_labels_are_tree_outputs() -> None:
    """The 2007 'training' octants are the decision tree's own verdicts, not human labels."""
    songs = load_training(TRAINING_CSV)
    assert len(songs) == 372
    assert all(classify_2007(s.features) == (s.octant, s.hevner) for s in songs)


def test_knn_leave_one_out_baseline() -> None:
    songs = load_training(TRAINING_CSV)
    x = np.stack([s.features.as_array() for s in songs])
    y = np.array([s.octant.value for s in songs])
    correct = 0
    for i, song in enumerate(songs):
        mask = np.arange(len(songs)) != i
        correct += knn_2007(song.features, x[mask], y[mask], k=5) == song.octant
    accuracy = correct / len(songs)
    # How well the thesis k-NN reproduces the tree it was trained on (recorded in legacy/README.md).
    assert accuracy == pytest.approx(BASELINE_LOO_ACCURACY, abs=1e-9), accuracy

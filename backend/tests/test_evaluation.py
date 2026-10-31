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


def test_roc_auc_and_average_precision_match_known_values() -> None:
    from moody.evaluation import average_precision, roc_auc

    # scikit-learn's documented example: roc_auc_score = 0.75, average_precision_score = 0.8333
    y, s = [0, 0, 1, 1], [0.1, 0.4, 0.35, 0.8]
    assert roc_auc(s, y) == pytest.approx(0.75)
    assert average_precision(s, y) == pytest.approx(0.8333, abs=1e-4)
    assert roc_auc([0.5, 0.5], [1, 0]) == pytest.approx(0.5)  # ties count half
    assert roc_auc([0.9, 0.1, 0.8], [1, 0, 1]) == 1.0
    assert average_precision([0.9, 0.1, 0.8], [1, 0, 1]) == 1.0
    assert average_precision([0.7, 0.7, 0.1], [1, 0, 0]) == pytest.approx(0.5)  # tied at the top
    assert np.isnan(roc_auc([0.1, 0.2], [1, 1]))
    assert np.isnan(average_precision([0.1, 0.2], [0, 0]))


def test_tag_evaluation_report() -> None:
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "tags_moodtheme", Path(__file__).parents[2] / "eval" / "tags_moodtheme.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rng = np.random.default_rng(0)
    truth = {i: ({"happy"} if i % 3 == 0 else {"sad"}) for i in range(60)}
    preds = {
        i: {
            "happy": float(("happy" in truth[i]) + rng.random()),
            "sad": float(rng.random()),
            "rare": 0.5,
        }
        for i in range(60)
    }
    preds[999] = {"happy": 1.0}  # not in the ground truth: ignored
    report = mod.evaluate(truth, preds)
    assert report["tracks"] == 60
    by_tag = {t["tag"]: t for t in report["per_tag"]}
    assert set(by_tag) == {"happy", "sad"}  # "rare" has no positives
    assert by_tag["happy"]["roc_auc"] > 0.9 and by_tag["happy"]["positives"] == 20
    assert 0.2 < by_tag["sad"]["roc_auc"] < 0.8  # random scores
    assert report["macro_roc_auc"] == pytest.approx(
        (by_tag["happy"]["roc_auc"] + by_tag["sad"]["roc_auc"]) / 2, abs=1e-4
    )

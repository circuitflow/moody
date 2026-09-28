from pathlib import Path

import pytest

from moody.analysis.analyzer import AnalysisError, FakeAnalyzer, TrackAnalysis
from moody.legacy.thesis2007 import Features2007
from tests.audio import write_tone


def test_fake_is_deterministic_and_in_range(tmp_path: Path) -> None:
    path = write_tone(tmp_path / "a.wav")
    first, second = FakeAnalyzer().analyze(path), FakeAnalyzer().analyze(path)
    assert first.valence == second.valence
    assert -1 <= first.valence <= 1 and -1 <= first.arousal <= 1
    assert all(-1 <= v <= 1 and -1 <= a <= 1 for _, v, a in first.segments)


def test_fake_failure(tmp_path: Path) -> None:
    path = write_tone(tmp_path / "bad.wav")
    with pytest.raises(AnalysisError):
        FakeAnalyzer(fail_on=frozenset({"bad.wav"})).analyze(path)


def test_top_tags_and_2007_verdict() -> None:
    analysis = TrackAnalysis(
        valence=0.5,
        arousal=0.5,
        segments=(),
        mood_probs={},
        tag_probs={"happy": 0.8, "calm": 0.05, "party": 0.3},
        features_2007=Features2007(mode=80, harmony=90, tempo=60, rhythm=80, loudness=70),
    )
    assert analysis.top_tags == ["happy", "party"]
    assert analysis.verdict_2007 == ("Excitement", "joyous")

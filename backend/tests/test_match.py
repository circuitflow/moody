import pytest

from moody.streaming.match import Candidate, best_match, core_artist, core_title, is_match


@pytest.mark.parametrize(
    ("raw", "core"),
    [
        ("Rain Song (2003 Remaster)", "rain song"),
        ("Rain Song - Remastered 2011", "rain song"),
        ("Rain Song [Live]", "rain song"),
        ("03 - Rain Song", "rain song"),
        ("Don't Stop", "don t stop"),
    ],
)
def test_core_title(raw: str, core: str) -> None:
    assert core_title(raw) == core


@pytest.mark.parametrize(
    ("raw", "core"),
    [
        ("The Weather", "weather"),
        ("Weather feat. Someone", "weather"),
        ("Weather & Friends", "weather"),
        ("Simon, Garfunkel", "simon"),
        ("Malcolm X", "malcolm x"),
    ],
)
def test_core_artist(raw: str, core: str) -> None:
    assert core_artist(raw) == core


def c(title: str, artist: str = "Weather", seconds: float | None = 200) -> Candidate:
    return Candidate(id=title, title=title, artists=(artist,), duration_s=seconds)


def test_is_match() -> None:
    assert is_match("Rain Song", "The Weather", 201, c("Rain Song - 2011 Remaster"))
    assert not is_match("Rain Song", "The Weather", 210, c("Rain Song"))  # 10 s off
    assert not is_match("Rain Song", "Other Band", 200, c("Rain Song"))
    assert not is_match("Snow Song", "The Weather", 200, c("Rain Song"))
    assert is_match("Rain Song", "The Weather", None, c("Rain Song"))  # no length: title + artist
    assert not is_match("Rain Song", None, None, c("Rain Song"))  # title alone is too weak
    assert is_match("Rain Song", None, 199, c("Rain Song"))  # title + length
    assert not is_match("", None, 200, c(""))


def test_best_match_keeps_relevance_order() -> None:
    hits = [c("Rain Song", seconds=400), c("Rain Song (Live)"), c("Rain Song")]
    best = best_match("Rain Song", "Weather", 200, hits)
    assert best is hits[1]

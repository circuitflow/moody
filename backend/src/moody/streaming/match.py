"""Matching library tracks to streaming-service tracks by artist, title and duration."""

from __future__ import annotations

import re
from dataclasses import dataclass

from moody.ingest.duplicates import normalize_title, strip_track_number

DURATION_TOLERANCE_S = 3.0

_BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_FEAT = re.compile(
    r"\s*[,;/]\s*.*$|\s+(?:feat\.?|ft\.?|featuring|with|&|\+|x)\s+.*$", re.IGNORECASE
)


def core_title(title: str) -> str:
    """Title without version notes: "Song (Remastered 2011) - Live" -> "song"."""
    head = _BRACKETS.sub(" ", strip_track_number(title)).split(" - ")[0]
    return normalize_title(head)


def core_artist(artist: str) -> str:
    """Main artist, normalized: "The Band feat. Someone" -> "band"."""
    main = _FEAT.sub("", artist.strip())
    name = normalize_title(main)
    return name.removeprefix("the ").strip()


@dataclass(frozen=True)
class Candidate:
    """A track on a streaming service, reduced to what matching needs."""

    id: str
    title: str
    artists: tuple[str, ...]
    duration_s: float | None
    isrc: str | None = None


def is_match(
    title: str, artist: str | None, duration_s: float | None, candidate: Candidate
) -> bool:
    if not title or core_title(candidate.title) != core_title(title):
        return False
    if artist and core_artist(artist) not in {core_artist(a) for a in candidate.artists}:
        return False
    if duration_s is not None and candidate.duration_s is not None:
        return abs(duration_s - candidate.duration_s) <= DURATION_TOLERANCE_S
    # Without both durations, a title-only match is too weak; title + artist is enough.
    return artist is not None


def best_match(
    title: str, artist: str | None, duration_s: float | None, candidates: list[Candidate]
) -> Candidate | None:
    """The first candidate (in the service's relevance order) that matches."""
    return next((c for c in candidates if is_match(title, artist, duration_s, c)), None)

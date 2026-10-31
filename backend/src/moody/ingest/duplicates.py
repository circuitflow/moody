"""Group copies of the same recording in different files (e.g. a WAV and an MP3).

Two files are copies when their titles match (from tags or file name, normalized) and their
durations agree within ``DURATION_TOLERANCE_S``, and either they sit in the same folder with the
same file name, or their Discogs-EffNet embeddings agree (cosine >= ``MIN_SIMILARITY``). The
embedding check keeps different recordings of a song (live, remix, cover) apart.

One copy per group becomes the primary (lossless first, then the larger file); the others get
``duplicate_of`` and are hidden from the catalog. Real tags from the alternates fill in primary
fields that were only derived from file or folder names. Files on disk are never touched.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from moody.analysis.models import EFFNET
from moody.store.db import from_blob
from moody.store.models import Embedding, Track

LOSSLESS = frozenset({".wav", ".flac", ".aiff", ".aif"})
DURATION_TOLERANCE_S = 2.0
MIN_SIMILARITY = 0.95
MERGED_FIELDS = ("title", "artist", "album", "isrc", "mb_recording_id")

_TRACK_NUMBER = re.compile(r"^\s*(?:\d{1,2}-)?\d{1,3}(?:\s*[-._]\s*|\s+)")
_NON_WORD = re.compile(r"[^\w]+")


def normalize_title(title: str) -> str:
    """Case-, punctuation- and track-number-insensitive title key."""
    return _NON_WORD.sub(" ", _TRACK_NUMBER.sub("", title).lower()).strip()


def _title_key(track: Track) -> str:
    return normalize_title(track.title or Path(track.path).stem)


def _derived(track: Track, field: str) -> bool:
    """True when a field holds a value guessed from the file or folder name, not a tag."""
    value = getattr(track, field)
    path = Path(track.path)
    if field == "title":
        return bool(value == path.stem)
    if field == "album":
        return bool(value == path.parent.name)
    if field == "artist":
        return bool(value == path.parent.parent.name)
    return False


def _primary_order(track: Track) -> tuple[bool, int, int]:
    return (Path(track.path).suffix.lower() not in LOSSLESS, -track.file_size, track.id)


@dataclass
class DedupeReport:
    groups: int = 0  # songs that have more than one file
    alternates: int = 0  # files hidden as copies
    changed: int = 0  # tracks whose duplicate_of changed in this run


def _same_file_name(a: Track, b: Track) -> bool:
    pa, pb = Path(a.path), Path(b.path)
    return pa.parent == pb.parent and pa.stem.lower() == pb.stem.lower()


def _durations_agree(a: Track, b: Track) -> bool:
    if a.duration_s is None or b.duration_s is None:
        return False
    return abs(a.duration_s - b.duration_s) <= DURATION_TOLERANCE_S


def find_groups(session: Session) -> list[list[Track]]:
    """Groups of 2+ tracks that are copies of the same recording, primary first."""
    blocks: dict[str, list[Track]] = defaultdict(list)
    for track in session.scalars(select(Track).order_by(Track.id)):
        key = _title_key(track)
        if key:
            blocks[key].append(track)
    candidates = [b for b in blocks.values() if len(b) > 1]
    if not candidates:
        return []

    ids = [t.id for block in candidates for t in block]
    vectors: dict[int, np.ndarray] = {}
    for track_id, blob in session.execute(
        select(Embedding.track_id, Embedding.vector).where(
            Embedding.model == EFFNET, Embedding.track_id.in_(ids)
        )
    ):
        v = from_blob(blob)
        norm = float(np.linalg.norm(v))
        if norm > 0:
            vectors[track_id] = v / norm

    def same_recording(a: Track, b: Track) -> bool:
        if not _durations_agree(a, b):
            return False
        if a.id in vectors and b.id in vectors:
            return float(vectors[a.id] @ vectors[b.id]) >= MIN_SIMILARITY
        return _same_file_name(a, b)  # not analyzed yet: only trust an exact file-name match

    groups: list[list[Track]] = []
    for block in candidates:
        sets = _DisjointSets([t.id for t in block])
        for i, a in enumerate(block):
            for b in block[i + 1 :]:
                if same_recording(a, b):
                    sets.union(a.id, b.id)
        clusters: dict[int, list[Track]] = defaultdict(list)
        for t in block:
            clusters[sets.find(t.id)].append(t)
        groups.extend(sorted(c, key=_primary_order) for c in clusters.values() if len(c) > 1)
    return groups


class _DisjointSets:
    def __init__(self, items: list[int]) -> None:
        self.parent = {i: i for i in items}

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)


def _merge_tags(primary: Track, alternates: list[Track]) -> None:
    for field in MERGED_FIELDS:
        if getattr(primary, field) is not None and not _derived(primary, field):
            continue
        tagged = [
            getattr(t, field)
            for t in alternates
            if getattr(t, field) is not None and not _derived(t, field)
        ]
        if tagged:
            setattr(primary, field, tagged[0])
        elif getattr(primary, field) is None:
            fallback = [getattr(t, field) for t in alternates if getattr(t, field) is not None]
            if fallback:
                setattr(primary, field, fallback[0])


def apply_duplicates(session: Session) -> DedupeReport:
    """Mark alternates, merge their tags into primaries, and clear stale marks. Commits."""
    groups = find_groups(session)
    desired: dict[int, int] = {}
    for primary, *alternates in groups:
        for alt in alternates:
            desired[alt.id] = primary.id
        _merge_tags(primary, alternates)

    report = DedupeReport(groups=len(groups), alternates=len(desired))
    for track in session.scalars(select(Track)):
        target = desired.get(track.id)
        if track.duplicate_of != target:
            track.duplicate_of = target
            report.changed += 1
    session.commit()
    return report

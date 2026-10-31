"""The public demo bundle: CC-licensed Jamendo tracks from the MTG-Jamendo mood/theme test split.

Pipeline (run in GitHub Actions, see ``.github/workflows/demo-bundle.yml``):

1. ``select``: read the split, look tracks up on the Jamendo API, keep CC BY / CC BY-SA ones that
   are still available, and pick a tag-stratified set (``tracks.csv``).
2. ``download``: fetch one shard's MP3s (resumable). Audio is analyzed, never rehosted.
3. ``moody scan`` per shard, then ``merge`` the shard databases and overwrite title, artist and
   album from Jamendo (the authoritative metadata for attribution).
4. ``export-static --attribution tracks.csv``: the static bundle, with credits and Jamendo stream
   URLs so the demo can play audio straight from Jamendo.
"""

from __future__ import annotations

import csv
import random
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx2
from sqlalchemy import Engine, MetaData, Table, insert, select, update
from sqlalchemy.orm import Session

from moody.store.models import Track

API = "https://api.jamendo.com/v3.0/tracks/"
TAG_PREFIX = "mood/theme---"
ALLOWED_LICENSES = ("by", "by-sa")  # NC and ND licenses can't go in a public showcase
MIN_DURATION_S = 60
MAX_DURATION_S = 600
LOOKUP_BATCH = 100
CSV_FIELDS = (
    "jamendo_id",
    "title",
    "artist",
    "album",
    "duration_s",
    "license_url",
    "share_url",
    "audio_url",
    "tags",
)


@dataclass(frozen=True)
class SplitTrack:
    jamendo_id: int
    duration_s: float
    tags: tuple[str, ...]  # without the "mood/theme---" prefix


@dataclass
class DemoTrack:
    jamendo_id: int
    title: str
    artist: str
    album: str
    duration_s: float
    license_url: str
    share_url: str
    audio_url: str
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def license_name(self) -> str:
        kind = license_kind(self.license_url) or "?"
        version = self.license_url.rstrip("/").rsplit("/", 1)[-1]
        return f"CC {kind.upper()} {version}"


def load_split(path: Path) -> list[SplitTrack]:
    """Rows of an MTG-Jamendo split TSV: ``TRACK_ID ARTIST_ID ALBUM_ID PATH DURATION TAGS...``."""
    out = []
    with path.open(newline="") as f:
        rows = csv.reader(f, delimiter="\t")
        next(rows)  # header
        for row in rows:
            if len(row) < 6:
                continue
            tags = tuple(t.removeprefix(TAG_PREFIX) for t in row[5:] if t.startswith(TAG_PREFIX))
            out.append(
                SplitTrack(
                    jamendo_id=int(row[0].removeprefix("track_")),
                    duration_s=float(row[4]),
                    tags=tags,
                )
            )
    return out


def license_kind(url: str) -> str | None:
    """``by``, ``by-sa``, ``by-nc``... from a creativecommons.org licence URL."""
    parts = url.lower().split("/licenses/", 1)
    if len(parts) != 2:
        return None
    return parts[1].split("/", 1)[0] or None


class JamendoError(RuntimeError):
    pass


class Jamendo:
    """The few Jamendo API v3 calls the demo needs. Free client ids: devportal.jamendo.com."""

    def __init__(
        self, http: httpx2.Client, client_id: str, sleep: Callable[[float], None] = time.sleep
    ) -> None:
        self.http = http
        self.client_id = client_id
        self.sleep = sleep

    def tracks(self, ids: Sequence[int]) -> list[dict[str, Any]]:
        """Metadata for up to 100 tracks; unavailable tracks are simply missing."""
        params: dict[str, str | int] = {
            "client_id": self.client_id,
            "format": "json",
            "limit": LOOKUP_BATCH,
            "id": " ".join(str(i) for i in ids),
            "audioformat": "mp32",
        }
        for attempt in range(4):
            resp = self.http.get(API, params=params)
            if resp.status_code in (429, 500, 502, 503):
                self.sleep(2.0 * (attempt + 1))
                continue
            data = resp.json()
            headers = data.get("headers") or {}
            if headers.get("status") != "success":
                raise JamendoError(str(headers.get("error_message") or f"HTTP {resp.status_code}"))
            results: list[dict[str, Any]] = data.get("results") or []
            return results
        raise JamendoError("Jamendo keeps failing; try again later")


def _demo_track(item: dict[str, Any], tags: tuple[str, ...]) -> DemoTrack | None:
    license_url = str(item.get("license_ccurl") or "")
    duration = float(item.get("duration") or 0)
    audio = str(item.get("audio") or "")
    if license_kind(license_url) not in ALLOWED_LICENSES or not audio:
        return None
    if not MIN_DURATION_S <= duration <= MAX_DURATION_S:
        return None
    return DemoTrack(
        jamendo_id=int(item["id"]),
        title=str(item.get("name") or "").strip(),
        artist=str(item.get("artist_name") or "").strip(),
        album=str(item.get("album_name") or "").strip(),
        duration_s=duration,
        license_url=license_url,
        share_url=str(item.get("shareurl") or f"https://www.jamendo.com/track/{item['id']}"),
        audio_url=audio,
        tags=tags,
    )


@dataclass
class SelectReport:
    in_split: int = 0
    available: int = 0
    licensed: int = 0
    selected: int = 0
    licenses: Counter[str] = field(default_factory=Counter)


def eligible_tracks(
    jamendo: Jamendo,
    split: Sequence[SplitTrack],
    on_batch: Callable[[int, int], None] | None = None,
) -> tuple[list[DemoTrack], SelectReport]:
    report = SelectReport(in_split=len(split))
    by_id = {t.jamendo_id: t for t in split}
    ids = sorted(by_id)
    found: list[DemoTrack] = []
    for start in range(0, len(ids), LOOKUP_BATCH):
        batch = ids[start : start + LOOKUP_BATCH]
        for item in jamendo.tracks(batch):
            tid = int(item.get("id") or 0)
            if tid not in by_id:
                continue
            report.available += 1
            report.licenses[license_kind(str(item.get("license_ccurl") or "")) or "?"] += 1
            track = _demo_track(item, by_id[tid].tags)
            if track is not None:
                found.append(track)
        if on_batch:
            on_batch(min(start + LOOKUP_BATCH, len(ids)), len(ids))
    report.licensed = len(found)
    return found, report


def stratify(tracks: Sequence[DemoTrack], n: int, seed: int = 0) -> list[DemoTrack]:
    """Up to ``n`` tracks, taking turns across tags from the rarest up, so every mood in the
    split is represented. Deterministic for a given input and seed."""
    rng = random.Random(seed)
    pools: dict[str, list[DemoTrack]] = defaultdict(list)
    for t in sorted(tracks, key=lambda t: t.jamendo_id):
        for tag in t.tags or ("(none)",):
            pools[tag].append(t)
    for pool in pools.values():
        rng.shuffle(pool)
    order = sorted(pools, key=lambda tag: (len(pools[tag]), tag))
    chosen: dict[int, DemoTrack] = {}
    while len(chosen) < n and any(pools.values()):
        for tag in order:
            pool = pools[tag]
            while pool and pool[-1].jamendo_id in chosen:
                pool.pop()
            if pool and len(chosen) < n:
                t = pool.pop()
                chosen[t.jamendo_id] = t
    return sorted(chosen.values(), key=lambda t: t.jamendo_id)


def write_csv(tracks: Iterable[DemoTrack], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for t in tracks:
            row = asdict(t)
            row["tags"] = " ".join(t.tags)
            w.writerow(row)


def read_csv(path: Path) -> list[DemoTrack]:
    with path.open(newline="") as f:
        return [
            DemoTrack(
                jamendo_id=int(r["jamendo_id"]),
                title=r["title"],
                artist=r["artist"],
                album=r["album"],
                duration_s=float(r["duration_s"]),
                license_url=r["license_url"],
                share_url=r["share_url"],
                audio_url=r["audio_url"],
                tags=tuple(r["tags"].split()),
            )
            for r in csv.DictReader(f)
        ]


def shard(tracks: Sequence[DemoTrack], index: int, count: int) -> list[DemoTrack]:
    if not 0 <= index < count:
        raise ValueError(f"shard {index} of {count}")
    return list(tracks[index::count])


@dataclass
class DownloadReport:
    downloaded: int = 0
    present: int = 0
    failed: list[int] = field(default_factory=list)


def download(
    tracks: Sequence[DemoTrack],
    dest: Path,
    http: httpx2.Client,
    *,
    workers: int = 4,
    sleep: Callable[[float], None] = time.sleep,
) -> DownloadReport:
    """Fetch ``{jamendo_id}.mp3`` files into ``dest``; existing files are kept (resumable)."""
    dest.mkdir(parents=True, exist_ok=True)
    report = DownloadReport()

    def one(t: DemoTrack) -> str:
        target = dest / f"{t.jamendo_id}.mp3"
        if target.exists() and target.stat().st_size > 0:
            return "present"
        part = target.with_suffix(".part")
        for attempt in range(3):
            try:
                with http.stream("GET", t.audio_url, follow_redirects=True) as resp:
                    if resp.status_code != 200:
                        raise httpx2.HTTPError(f"HTTP {resp.status_code}")
                    with part.open("wb") as f:
                        for chunk in resp.iter_bytes():
                            f.write(chunk)
                if part.stat().st_size == 0:
                    raise httpx2.HTTPError("empty response")
                part.replace(target)
                return "downloaded"
            except httpx2.HTTPError:
                part.unlink(missing_ok=True)
                sleep(2.0 * (attempt + 1))
        return "failed"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for t, outcome in zip(tracks, pool.map(one, tracks), strict=True):
            if outcome == "downloaded":
                report.downloaded += 1
            elif outcome == "present":
                report.present += 1
            else:
                report.failed.append(t.jamendo_id)
    return report


# Merging shard databases -------------------------------------------------------------------

# Tables copied from each shard, children after tracks. Their ``track_id`` is remapped.
_CHILD_TABLES = ("analyses", "segments", "embeddings")


def merge(sources: Sequence[Engine], target: Engine) -> int:
    """Copy tracks and their analyses, segments and embeddings from shard databases into
    ``target`` (already migrated), giving tracks new ids. Returns the number of tracks copied."""
    copied = 0
    with target.begin() as dst:
        meta = MetaData()
        tracks = Table("tracks", meta, autoload_with=dst)
        children = {name: Table(name, meta, autoload_with=dst) for name in _CHILD_TABLES}
        next_id = (dst.execute(select(tracks.c.id).order_by(tracks.c.id.desc())).scalar() or 0) + 1
        hashes = set(dst.execute(select(tracks.c.content_hash)).scalars())
        for src_engine in sources:
            with src_engine.connect() as src:
                id_map: dict[int, int] = {}
                for row in src.execute(select(tracks).where(tracks.c.duplicate_of.is_(None))):
                    values = dict(row._mapping)
                    if values["content_hash"] in hashes:
                        continue  # the same file under two Jamendo ids
                    hashes.add(values["content_hash"])
                    id_map[values["id"]] = next_id
                    values["id"] = next_id
                    dst.execute(insert(tracks).values(**values))
                    next_id += 1
                    copied += 1
                for table in children.values():
                    for row in src.execute(select(table)):
                        values = dict(row._mapping)
                        new_id = id_map.get(values["track_id"])
                        if new_id is not None:
                            values["track_id"] = new_id
                            dst.execute(insert(table).values(**values))
    return copied


def jamendo_id_of(path: str) -> int | None:
    stem = Path(path).stem
    return int(stem) if stem.isdigit() else None


def apply_metadata(session: Session, demo: Sequence[DemoTrack]) -> int:
    """Jamendo's title, artist and album replace whatever the MP3 tags said. Commits."""
    by_id = {t.jamendo_id: t for t in demo}
    changed = 0
    for track_id, path in session.execute(select(Track.id, Track.path)).all():
        d = by_id.get(jamendo_id_of(path) or -1)
        if d is None:
            continue
        session.execute(
            update(Track)
            .where(Track.id == track_id)
            .values(title=d.title or None, artist=d.artist or None, album=d.album or None)
        )
        changed += 1
    session.commit()
    return changed

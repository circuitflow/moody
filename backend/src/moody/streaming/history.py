"""Listening history: importing plays from several sources and matching them to the library.

Plays from different sources overlap (Spotify plays are often scrobbled to Last.fm too), so a
play counts once: the same artist and title within ``SAME_PLAY_S`` seconds is a duplicate,
whatever the source. Only plays matched to an analyzed library track can be placed on the mood
map. Moody needs the audio, so coverage is reported with every import.
"""

from __future__ import annotations

import bisect
import json
import zipfile
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from moody.store.models import Analysis, ExternalId, Play, Track
from moody.streaming.match import core_artist, core_title

SAME_PLAY_S = 30
MIN_MS_PLAYED = 30_000  # a "play" by the common scrobbling rule: at least 30 seconds


@dataclass(frozen=True)
class PlayRecord:
    source: str
    played_at: datetime  # aware, UTC, start of the listen
    title: str
    artist: str | None = None
    album: str | None = None
    ms_played: int | None = None
    external_id: str | None = None
    mbid: str | None = None


def as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def play_key(artist: str | None, title: str) -> tuple[str, str]:
    return (core_artist(artist) if artist else "", core_title(title))


class LibraryIndex:
    """Lookups from play metadata to library tracks (primary copies only)."""

    def __init__(self, session: Session) -> None:
        self.by_mbid: dict[str, int] = {}
        self.by_key: dict[tuple[str, str], int] = {}
        rows = session.execute(
            select(Track.id, Track.title, Track.artist, Track.path, Track.mb_recording_id)
            .where(Track.duplicate_of.is_(None))
            .order_by(Track.id)
        )
        for track_id, title, artist, path, mbid in rows:
            if mbid:
                self.by_mbid.setdefault(mbid, track_id)
            name = title or Path(path).stem
            if artist and name:
                self.by_key.setdefault(play_key(artist, name), track_id)
        self.by_uri = {
            uri: track_id
            for track_id, uri in session.execute(
                select(ExternalId.track_id, ExternalId.external_id).where(
                    ExternalId.provider == "spotify"
                )
            )
        }

    def match(
        self, artist: str | None, title: str, mbid: str | None, external_id: str | None
    ) -> int | None:
        if mbid and mbid in self.by_mbid:
            return self.by_mbid[mbid]
        if external_id and external_id in self.by_uri:
            return self.by_uri[external_id]
        if not artist:
            return None
        return self.by_key.get(play_key(artist, title))


@dataclass
class ImportReport:
    source: str
    new: int = 0
    duplicates: int = 0
    skipped: int = 0  # too short, podcasts, or without a title
    newest: datetime | None = None
    more: bool = False  # stopped at a page limit; call again to continue


@dataclass
class _Seen:
    """Existing plays by (artist, title) key, as sorted timestamps, for duplicate checks."""

    times: dict[tuple[str, str], list[float]] = field(default_factory=lambda: defaultdict(list))

    @classmethod
    def load(cls, session: Session) -> _Seen:
        seen = cls()
        for artist, title, played_at in session.execute(
            select(Play.artist, Play.title, Play.played_at)
        ):
            seen.times[play_key(artist, title)].append(as_utc(played_at).timestamp())
        for ts in seen.times.values():
            ts.sort()
        return seen

    def has(self, key: tuple[str, str], t: float) -> bool:
        ts = self.times.get(key)
        if not ts:
            return False
        i = bisect.bisect_left(ts, t - SAME_PLAY_S)
        return i < len(ts) and ts[i] <= t + SAME_PLAY_S

    def add(self, key: tuple[str, str], t: float) -> None:
        bisect.insort(self.times[key], t)


def ingest(session: Session, records: Iterable[PlayRecord], report: ImportReport) -> ImportReport:
    """Store new plays (skipping duplicates across all sources) and match them. Commits."""
    seen = _Seen.load(session)
    library = LibraryIndex(session)
    batch: list[Play] = []
    for rec in records:
        if not rec.title.strip() or (rec.ms_played is not None and rec.ms_played < MIN_MS_PLAYED):
            report.skipped += 1
            continue
        key = play_key(rec.artist, rec.title)
        t = as_utc(rec.played_at).timestamp()
        if seen.has(key, t):
            report.duplicates += 1
            continue
        seen.add(key, t)
        batch.append(
            Play(
                source=rec.source,
                played_at=as_utc(rec.played_at),
                artist=rec.artist,
                title=rec.title,
                album=rec.album,
                ms_played=rec.ms_played,
                external_id=rec.external_id,
                mbid=rec.mbid,
                track_id=library.match(rec.artist, rec.title, rec.mbid, rec.external_id),
            )
        )
        report.new += 1
        if report.newest is None or as_utc(rec.played_at) > report.newest:
            report.newest = as_utc(rec.played_at)
        if len(batch) >= 1000:
            session.add_all(batch)
            session.commit()
            batch = []
    session.add_all(batch)
    session.commit()
    return report


def rematch(session: Session) -> int:
    """Match plays that weren't matched before (e.g. after scanning more music), and move plays
    of copies that are now hidden as duplicates to the copy Moody uses. Commits."""
    for alt, primary in session.execute(
        select(Track.id, Track.duplicate_of).where(Track.duplicate_of.is_not(None))
    ).all():
        session.execute(update(Play).where(Play.track_id == alt).values(track_id=primary))
    library = LibraryIndex(session)
    changed = 0
    for play in session.scalars(select(Play).where(Play.track_id.is_(None))):
        track_id = library.match(play.artist, play.title, play.mbid, play.external_id)
        if track_id is not None:
            play.track_id = track_id
            changed += 1
    session.commit()
    return changed


@dataclass
class SourceCoverage:
    plays: int
    matched: int
    first: datetime | None
    last: datetime | None


def coverage(session: Session) -> dict[str, SourceCoverage]:
    rows = session.execute(
        select(
            Play.source,
            func.count(),
            func.count(Play.track_id),
            func.min(Play.played_at),
            func.max(Play.played_at),
        ).group_by(Play.source)
    )
    return {
        source: SourceCoverage(
            plays=n,
            matched=matched,
            first=as_utc(first) if first else None,
            last=as_utc(last) if last else None,
        )
        for source, n, matched, first, last in rows
    }


def latest(session: Session, source: str) -> datetime | None:
    value = session.scalar(select(func.max(Play.played_at)).where(Play.source == source))
    return as_utc(value) if value else None


# Spotify "Download your data" files ------------------------------------------------------


def _spotify_extended(item: dict[str, Any]) -> PlayRecord | None:
    """One entry of Streaming_History_Audio_*.json (the extended, lifetime history)."""
    title = item.get("master_metadata_track_name")
    if not title or not item.get("ts"):
        return None  # podcasts and audiobooks have no track name
    ms = int(item.get("ms_played") or 0)
    ended = datetime.fromisoformat(str(item["ts"]).replace("Z", "+00:00"))
    return PlayRecord(
        source="spotify-export",
        played_at=as_utc(ended) - timedelta(milliseconds=ms),  # ts is when playback stopped
        title=str(title),
        artist=item.get("master_metadata_album_artist_name"),
        album=item.get("master_metadata_album_album_name"),
        ms_played=ms,
        external_id=item.get("spotify_track_uri"),
    )


def _spotify_account(item: dict[str, Any]) -> PlayRecord | None:
    """One entry of StreamingHistory_music_*.json (the basic, last-year history)."""
    title = item.get("trackName")
    if not title or not item.get("endTime"):
        return None
    ms = int(item.get("msPlayed") or 0)
    ended = datetime.strptime(str(item["endTime"]), "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
    return PlayRecord(
        source="spotify-export",
        played_at=ended - timedelta(milliseconds=ms),
        title=str(title),
        artist=item.get("artistName"),
        ms_played=ms,
    )


def _history_files(path: Path) -> Iterator[tuple[str, bytes]]:
    prefixes = ("Streaming_History_Audio", "endsong", "StreamingHistory_music", "StreamingHistory")

    def wanted(name: str) -> bool:
        return Path(name).name.startswith(prefixes) and name.endswith(".json")

    if path.is_file() and path.suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            for name in sorted(zf.namelist()):
                if wanted(name):
                    yield name, zf.read(name)
    elif path.is_file():
        yield path.name, path.read_bytes()
    else:
        for file in sorted(path.rglob("*.json")):
            if wanted(file.name):
                yield file.name, file.read_bytes()


def read_spotify_export(path: Path) -> Iterator[PlayRecord | None]:
    """Plays from a Spotify data download: a .zip, a folder, or one JSON file.

    Yields None for entries that aren't music (podcasts, audiobooks), so they can be counted.
    """
    found = False
    for _name, data in _history_files(path):
        items = json.loads(data)
        if not isinstance(items, list):
            continue
        found = True
        for item in items:
            if not isinstance(item, dict):
                continue
            yield _spotify_extended(item) if "ts" in item else _spotify_account(item)
    if not found:
        raise FileNotFoundError(
            f"no Spotify history files in {path} "
            "(expected Streaming_History_Audio_*.json or StreamingHistory_music_*.json)"
        )


def import_records(
    session: Session, source: str, records: Iterable[PlayRecord | None]
) -> ImportReport:
    """Ingest an iterable where None marks an entry that isn't a play."""
    report = ImportReport(source=source)

    def plays() -> Iterator[PlayRecord]:
        for rec in records:
            if rec is None:
                report.skipped += 1
            else:
                yield rec

    return ingest(session, plays(), report)


# Mood over time ---------------------------------------------------------------------------


@dataclass
class Bucket:
    key: str
    plays: int = 0
    matched: int = 0
    valence_sum: float = 0.0
    arousal_sum: float = 0.0

    @property
    def valence(self) -> float | None:
        return round(self.valence_sum / self.matched, 4) if self.matched else None

    @property
    def arousal(self) -> float | None:
        return round(self.arousal_sum / self.matched, 4) if self.matched else None


def mood_buckets(
    session: Session, bucket: str, tz: ZoneInfo, since: datetime | None = None
) -> list[Bucket]:
    """Plays-weighted mean valence/arousal per local week (every week from the first play to
    the last, empty ones included) or per local hour of day (all 24)."""
    query = (
        select(Play.played_at, Analysis.valence, Analysis.arousal)
        .outerjoin(Analysis, Analysis.track_id == Play.track_id)
        .order_by(Play.played_at)
    )
    if since is not None:
        query = query.where(Play.played_at >= since.astimezone(UTC).replace(tzinfo=None))
    rows = session.execute(query).all()
    if bucket == "hour":
        buckets = {str(h): Bucket(str(h)) for h in range(24)}
    else:
        buckets = {}
        if rows:
            first = _week_start(as_utc(rows[0][0]).astimezone(tz))
            last = _week_start(as_utc(rows[-1][0]).astimezone(tz))
            day = first
            while day <= last:
                buckets[day.isoformat()] = Bucket(day.isoformat())
                day += timedelta(days=7)
    for played_at, valence, arousal in rows:
        local = as_utc(played_at).astimezone(tz)
        key = str(local.hour) if bucket == "hour" else _week_start(local).isoformat()
        b = buckets[key]
        b.plays += 1
        if valence is not None and arousal is not None:
            b.matched += 1
            b.valence_sum += valence
            b.arousal_sum += arousal
    return list(buckets.values())


def _week_start(local: datetime) -> date:
    d = local.date()
    return d - timedelta(days=d.weekday())


def top_tracks(
    session: Session, limit: int = 10, since: datetime | None = None
) -> list[tuple[Track, int]]:
    """Most-played library tracks (matched plays only)."""
    n = func.count(Play.id).label("n")
    query = (
        select(Track, n)
        .join(Play, Play.track_id == Track.id)
        .group_by(Track.id)
        .order_by(n.desc(), Track.id)
        .limit(limit)
        .options(selectinload(Track.analysis))
    )
    if since is not None:
        query = query.where(Play.played_at >= since.astimezone(UTC).replace(tzinfo=None))
    return [(track, int(count)) for track, count in session.execute(query)]

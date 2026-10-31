"""Saved playlists: queries shared by the API and the CLI, and M3U export."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from moody.api.queries import summary
from moody.api.schemas import PlaylistCreate, PlaylistDetail, PlaylistSummary
from moody.store.models import Playlist, PlaylistItem, Track


class UnknownTracks(ValueError):
    def __init__(self, ids: Sequence[int]) -> None:
        super().__init__(f"unknown track ids: {', '.join(map(str, ids))}")
        self.ids = list(ids)


def _point(v: float | None, a: float | None) -> tuple[float, float] | None:
    return None if v is None or a is None else (v, a)


def as_utc(dt: datetime) -> datetime:
    """SQLite drops time zones; stored times are UTC, so say so on the way out."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _summary(p: Playlist, count: int) -> PlaylistSummary:
    return PlaylistSummary(
        id=p.id,
        name=p.name,
        created_at=as_utc(p.created_at),
        count=count,
        start=(p.start_valence, p.start_arousal),
        end=(p.end_valence, p.end_arousal),
        via=_point(p.via_valence, p.via_arousal),
    )


def create(session: Session, body: PlaylistCreate) -> PlaylistDetail:
    known = set(session.scalars(select(Track.id).where(Track.id.in_(body.track_ids))))
    missing = [t for t in body.track_ids if t not in known]
    if missing:
        raise UnknownTracks(missing)
    playlist = Playlist(
        name=body.name,
        start_valence=body.start[0],
        start_arousal=body.start[1],
        end_valence=body.end[0],
        end_arousal=body.end[1],
        via_valence=body.via[0] if body.via else None,
        via_arousal=body.via[1] if body.via else None,
        params=body.params,
        items=[PlaylistItem(position=i, track_id=t) for i, t in enumerate(body.track_ids)],
    )
    session.add(playlist)
    session.commit()
    detail = get(session, playlist.id)
    assert detail is not None
    return detail


def list_all(session: Session) -> list[PlaylistSummary]:
    counts = (
        select(PlaylistItem.playlist_id, func.count().label("n"))
        .group_by(PlaylistItem.playlist_id)
        .subquery()
    )
    rows = session.execute(
        select(Playlist, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.playlist_id == Playlist.id)
        .order_by(Playlist.created_at.desc(), Playlist.id.desc())
    ).all()
    return [_summary(p, int(n)) for p, n in rows]


def _load(session: Session, playlist_id: int) -> Playlist | None:
    return session.get(
        Playlist,
        playlist_id,
        options=[
            selectinload(Playlist.items)
            .selectinload(PlaylistItem.track)
            .selectinload(Track.analysis)
        ],
    )


def get(session: Session, playlist_id: int) -> PlaylistDetail | None:
    p = _load(session, playlist_id)
    if p is None:
        return None
    return PlaylistDetail(
        **_summary(p, len(p.items)).model_dump(),
        params=p.params,
        tracks=[summary(item.track) for item in p.items],
    )


def delete(session: Session, playlist_id: int) -> bool:
    p = session.get(Playlist, playlist_id)
    if p is None:
        return False
    session.delete(p)
    session.commit()
    return True


def _clean(text: str) -> str:
    """One line of M3U text: no line breaks, which would start a new entry."""
    return " ".join(text.split())


def to_m3u(session: Session, playlist_id: int) -> tuple[str, str] | None:
    """(file name, M3U8 text) with absolute paths, for Apple Music, VLC and most players."""
    p = _load(session, playlist_id)
    if p is None:
        return None
    lines = ["#EXTM3U", f"#PLAYLIST:{_clean(p.name)}"]
    for item in p.items:
        t = item.track
        seconds = round(t.duration_s) if t.duration_s is not None else -1
        label = " - ".join(x for x in (t.artist, t.title or Path(t.path).stem) if x)
        lines += [f"#EXTINF:{seconds},{_clean(label)}", t.path]
    filename = (
        "".join(c if c.isalnum() or c in " -_" else "_" for c in p.name).strip() or "playlist"
    )
    return f"{filename}.m3u8", "\n".join(lines) + "\n"

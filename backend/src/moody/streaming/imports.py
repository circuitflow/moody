"""History imports, shared by the CLI and the API."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx2
from sqlalchemy.orm import Session

from moody.streaming import history, lastfm, spotify
from moody.streaming.history import ImportReport, PlayRecord


def import_lastfm(
    session: Session,
    http: httpx2.Client,
    api_key: str,
    user: str,
    *,
    full: bool = False,
    max_pages: int | None = None,
    on_page: Callable[[int, int], None] | None = None,
) -> ImportReport:
    """New scrobbles since the last import (everything with ``full``), oldest first."""
    since = None if full else history.latest(session, "lastfm")
    progress = [0, 0]

    def track(done: int, total: int) -> None:
        progress[:] = [done, total]
        if on_page:
            on_page(done, total)

    def records() -> Iterator[PlayRecord]:
        for page in lastfm.recent_tracks(
            http,
            api_key,
            user,
            since=since,
            until=datetime.now(UTC),
            max_pages=max_pages,
            on_page=track,
        ):
            yield from page

    report = history.ingest(session, records(), ImportReport(source="lastfm"))
    report.more = progress[0] < progress[1]
    return report


def import_spotify_recent(session: Session, client: spotify.SpotifyClient) -> ImportReport:
    """The last 50 Spotify plays (the API keeps no more), skipping ones already imported."""
    since = history.latest(session, "spotify")
    return history.ingest(
        session, spotify.recently_played(client, since), ImportReport(source="spotify")
    )


def import_spotify_export(session: Session, path: Path) -> ImportReport:
    return history.import_records(session, "spotify-export", history.read_spotify_export(path))

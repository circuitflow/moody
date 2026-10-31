"""Last.fm scrobble history via ``user.getRecentTracks`` (an API key is enough)."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import httpx2

from moody.streaming.history import PlayRecord

API = "https://ws.audioscrobbler.com/2.0/"
PAGE_SIZE = 200  # the API maximum
MIN_INTERVAL_S = 0.25  # Last.fm asks for at most 5 requests per second
RATE_LIMITED = 29


class LastfmError(RuntimeError):
    pass


def _text(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("#text") or value.get("name")
    return str(value) if value else None


def _record(item: dict[str, Any]) -> PlayRecord | None:
    if (item.get("@attr") or {}).get("nowplaying"):
        return None  # still playing: no timestamp yet
    uts = (item.get("date") or {}).get("uts")
    title = item.get("name")
    if not uts or not title:
        return None
    return PlayRecord(
        source="lastfm",
        played_at=datetime.fromtimestamp(int(uts), tz=UTC),
        title=str(title),
        artist=_text(item.get("artist")),
        album=_text(item.get("album")),
        mbid=item.get("mbid") or None,
    )


def recent_tracks(
    http: httpx2.Client,
    api_key: str,
    user: str,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    max_pages: int | None = None,
    on_page: Callable[[int, int], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[list[PlayRecord]]:
    """Pages of plays in (``since``, ``until``], oldest page first.

    Oldest first, so an import stopped by ``max_pages`` leaves only newer plays for the next
    run, which continues from the newest play imported. A fixed ``until`` keeps the pages
    stable while new scrobbles arrive. ``on_page(done, total)`` reports progress.
    """
    last_call = [0.0]

    def fetch(page: int) -> tuple[list[PlayRecord], int]:
        wait = MIN_INTERVAL_S - (time.monotonic() - last_call[0])
        if wait > 0:
            sleep(wait)
        params: dict[str, str | int] = {
            "method": "user.getrecenttracks",
            "user": user,
            "api_key": api_key,
            "format": "json",
            "limit": PAGE_SIZE,
            "page": page,
        }
        if since is not None:
            params["from"] = int(since.timestamp()) + 1
        if until is not None:
            params["to"] = int(until.timestamp())
        last_call[0] = time.monotonic()
        block = _get(http, params, sleep).get("recenttracks") or {}
        total = int((block.get("@attr") or {}).get("totalPages") or 0)
        items = block.get("track") or []
        if isinstance(items, dict):  # a single play comes back as an object
            items = [items]
        return [r for r in map(_record, items) if r is not None], total

    newest, total = fetch(1)  # page 1 is the newest; it also says how many pages there are
    if total <= 1:
        if on_page:
            on_page(1, 1)
        yield newest
        return
    done = 0
    for page in range(total, 1, -1):
        if max_pages is not None and done >= max_pages:
            return
        records, _ = fetch(page)
        done += 1
        if on_page:
            on_page(done, total)
        yield records
    if max_pages is not None and done >= max_pages:
        return
    if on_page:
        on_page(total, total)
    yield newest


def _get(
    http: httpx2.Client, params: dict[str, str | int], sleep: Callable[[float], None]
) -> dict[str, Any]:
    for attempt in range(4):
        resp = http.get(API, params=params)
        try:
            data: dict[str, Any] = resp.json()
        except ValueError:
            data = {}
        error = data.get("error")
        if error == RATE_LIMITED or resp.status_code in (429, 500, 502, 503):
            sleep(2.0 * (attempt + 1))
            continue
        if error:
            raise LastfmError(str(data.get("message") or f"Last.fm error {error}"))
        if resp.status_code != 200:
            raise LastfmError(f"Last.fm: HTTP {resp.status_code}")
        return data
    raise LastfmError("Last.fm is rate-limiting requests; try again in a few minutes")

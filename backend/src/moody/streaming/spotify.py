"""Spotify Web API: PKCE sign-in, token refresh, track matching and playlist export.

Spotify is used only for identity (search, ISRC), history (recently played) and output
(playlists). Moody never touches Spotify audio. Since February 2026, Development Mode apps need
the owner to have Premium and allow 5 users; playlists are created with ``POST /me/playlists``
and filled with ``POST /playlists/{id}/items``.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx2
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from moody.store.models import ExternalId, OAuthToken, Playlist, PlaylistItem, Track
from moody.streaming.history import PlayRecord
from moody.streaming.match import Candidate, best_match

PROVIDER = "spotify"
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"
SCOPES = "user-read-recently-played user-top-read playlist-modify-private playlist-modify-public"
SEARCH_LIMIT = 10  # the Development Mode maximum since February 2026
ADD_BATCH = 100
STATE_TTL_S = 600


class SpotifyError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class NotConnected(SpotifyError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def pkce_pair() -> tuple[str, str]:
    """(code_verifier, S256 code_challenge)."""
    verifier = secrets.token_urlsafe(64)[:96]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@dataclass
class PendingLogins:
    """Sign-ins in progress (state -> verifier and where to return). One process, one user."""

    entries: dict[str, tuple[str, str, float]] = field(default_factory=dict)

    def add(self, verifier: str, return_to: str) -> str:
        now = time.monotonic()
        self.entries = {k: v for k, v in self.entries.items() if now - v[2] < STATE_TTL_S}
        state = secrets.token_urlsafe(24)
        self.entries[state] = (verifier, return_to, now)
        return state

    def pop(self, state: str) -> tuple[str, str] | None:
        entry = self.entries.pop(state, None)
        if entry is None or time.monotonic() - entry[2] >= STATE_TTL_S:
            return None
        return entry[0], entry[1]


def authorize_url(client_id: str, redirect_uri: str, state: str, challenge: str) -> str:
    query = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": state,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    }
    return f"{AUTH_URL}?{urlencode(query)}"


def _error_message(resp: httpx2.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return f"HTTP {resp.status_code}"
    err = body.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or f"HTTP {resp.status_code}")
    return str(body.get("error_description") or err or f"HTTP {resp.status_code}")


def _store_tokens(
    session: Session, payload: dict[str, Any], account: dict[str, Any] | None
) -> None:
    row = session.get(OAuthToken, PROVIDER)
    expires_at = _now() + timedelta(seconds=int(payload.get("expires_in", 3600)))
    if row is None:
        row = OAuthToken(provider=PROVIDER, access_token="", expires_at=expires_at)
        session.add(row)
    row.access_token = payload["access_token"]
    # Refresh responses may omit the refresh token, which then stays valid.
    row.refresh_token = payload.get("refresh_token") or row.refresh_token
    row.expires_at = expires_at
    row.scope = payload.get("scope", row.scope or "")
    if account is not None:
        row.account_id = account.get("id")
        row.account_name = account.get("display_name") or account.get("id")
    row.updated_at = _now()
    session.commit()


def exchange_code(
    session: Session,
    http: httpx2.Client,
    *,
    client_id: str,
    redirect_uri: str,
    code: str,
    verifier: str,
) -> str:
    """Finish the sign-in: trade the code for tokens and store them. Returns the account name."""
    resp = http.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier,
        },
    )
    if resp.status_code != 200:
        raise SpotifyError(f"sign-in failed: {_error_message(resp)}", resp.status_code)
    payload = resp.json()
    me = http.get(f"{API}/me", headers={"Authorization": f"Bearer {payload['access_token']}"})
    account = me.json() if me.status_code == 200 else None
    _store_tokens(session, payload, account)
    return str((account or {}).get("display_name") or (account or {}).get("id") or "Spotify")


def disconnect(session: Session) -> None:
    row = session.get(OAuthToken, PROVIDER)
    if row is not None:
        session.delete(row)
        session.commit()


class SpotifyClient:
    """Authenticated calls with automatic token refresh and 429 back-off."""

    def __init__(
        self,
        session: Session,
        http: httpx2.Client,
        client_id: str,
        *,
        sleep: Any = time.sleep,
    ) -> None:
        self.session = session
        self.http = http
        self.client_id = client_id
        self.sleep = sleep

    def _token(self, force_refresh: bool = False) -> str:
        row = self.session.get(OAuthToken, PROVIDER)
        if row is None:
            raise NotConnected("Spotify is not connected")
        if force_refresh or _aware(row.expires_at) - timedelta(seconds=60) <= _now():
            if not row.refresh_token:
                raise NotConnected("Spotify sign-in expired; connect again")
            resp = self.http.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": row.refresh_token,
                    "client_id": self.client_id,
                },
            )
            if resp.status_code != 200:
                disconnect(self.session)
                raise NotConnected(
                    f"Spotify sign-in expired ({_error_message(resp)}); connect again"
                )
            _store_tokens(self.session, resp.json(), None)
            row = self.session.get(OAuthToken, PROVIDER)
            assert row is not None
        return row.access_token

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        refreshed = False
        for _attempt in range(5):
            headers = {"Authorization": f"Bearer {self._token(force_refresh=refreshed)}"}
            resp = self.http.request(method, f"{API}{path}", headers=headers, **kwargs)
            if resp.status_code == 401 and not refreshed:
                refreshed = True
                continue
            if resp.status_code == 429:
                self.sleep(min(float(resp.headers.get("Retry-After", "1")), 30.0))
                continue
            if resp.status_code >= 400:
                raise SpotifyError(_error_message(resp), resp.status_code)
            return resp.json() if resp.content else None
        raise SpotifyError("Spotify is rate-limiting requests; try again in a minute", 429)

    def search_tracks(self, query: str) -> list[Candidate]:
        data = self.request(
            "GET",
            "/search",
            params={"q": query, "type": "track", "limit": SEARCH_LIMIT, "market": "from_token"},
        )
        return [
            _candidate(item) for item in (data or {}).get("tracks", {}).get("items", []) if item
        ]


def _candidate(item: dict[str, Any]) -> Candidate:
    duration_ms = item.get("duration_ms")
    return Candidate(
        id=str(item["uri"]),
        title=str(item.get("name") or ""),
        artists=tuple(str(a.get("name") or "") for a in item.get("artists") or []),
        duration_s=duration_ms / 1000 if isinstance(duration_ms, int | float) else None,
        isrc=(item.get("external_ids") or {}).get("isrc"),
    )


def _query_value(text: str) -> str:
    """Field values can't contain quotes or field syntax."""
    return " ".join(text.replace('"', " ").replace(":", " ").split())


def match_track(client: SpotifyClient, track: Track) -> tuple[str, str] | None:
    """(Spotify URI, how) for a library track: ISRC first, then artist + title + duration."""
    if track.isrc:
        hits = client.search_tracks(f"isrc:{_query_value(track.isrc)}")
        exact = [c for c in hits if c.isrc is None or c.isrc.upper() == track.isrc.upper()]
        if exact:
            return exact[0].id, "isrc"
    title = track.title or Path(track.path).stem
    if not title:
        return None
    query = f"track:{_query_value(title)}"
    if track.artist:
        query += f" artist:{_query_value(track.artist)}"
    hit = best_match(title, track.artist, track.duration_s, client.search_tracks(query))
    return (hit.id, "search") if hit else None


@dataclass
class ExportResult:
    url: str
    name: str
    matched: int
    unmatched: list[Track]


def export_playlist(session: Session, client: SpotifyClient, playlist_id: int) -> ExportResult:
    playlist = session.get(
        Playlist,
        playlist_id,
        options=[selectinload(Playlist.items).selectinload(PlaylistItem.track)],
    )
    if playlist is None:
        raise LookupError("playlist not found")
    tracks = [item.track for item in playlist.items]
    cached = {
        row.track_id: row.external_id
        for row in session.scalars(
            select(ExternalId).where(
                ExternalId.provider == PROVIDER, ExternalId.track_id.in_([t.id for t in tracks])
            )
        )
    }
    uris: list[str] = []
    unmatched: list[Track] = []
    for track in tracks:
        uri = cached.get(track.id)
        if uri is None:
            found = match_track(client, track)
            if found is not None:
                uri = found[0]
                session.add(
                    ExternalId(
                        track_id=track.id, provider=PROVIDER, external_id=uri, matched_by=found[1]
                    )
                )
                session.commit()
        if uri is None:
            unmatched.append(track)
        elif uri not in uris:
            uris.append(uri)
    if not uris:
        raise SpotifyError("none of the tracks were found on Spotify")
    description = "A mood path made with Moody (github.com/circuitflow/moody)."
    created = client.request(
        "POST",
        "/me/playlists",
        json={"name": playlist.name, "description": description, "public": False},
    )
    for i in range(0, len(uris), ADD_BATCH):
        client.request(
            "POST", f"/playlists/{created['id']}/items", json={"uris": uris[i : i + ADD_BATCH]}
        )
    url = str((created.get("external_urls") or {}).get("spotify") or "")
    return ExportResult(
        url=url,
        name=str(created.get("name") or playlist.name),
        matched=len(uris),
        unmatched=unmatched,
    )


def recently_played(client: SpotifyClient, after: datetime | None = None) -> list[PlayRecord]:
    """Up to the last 50 plays (all the API keeps), oldest first.

    Spotify's ``played_at`` is when playback ended; subtracting the track length gives the start,
    which is what Last.fm stamps scrobbles with, so a play in both sources counts once.
    """
    params: dict[str, int] = {"limit": 50}
    if after is not None:
        params["after"] = int(after.timestamp() * 1000)
    data = client.request("GET", "/me/player/recently-played", params=params) or {}
    records = []
    for item in data.get("items") or []:
        track = item.get("track") or {}
        if not track.get("name") or not item.get("played_at"):
            continue
        ended = datetime.fromisoformat(str(item["played_at"]).replace("Z", "+00:00"))
        duration_ms = int(track.get("duration_ms") or 0)
        artists = track.get("artists") or [{}]
        records.append(
            PlayRecord(
                source="spotify",
                played_at=_aware(ended) - timedelta(milliseconds=duration_ms),
                title=str(track["name"]),
                artist=artists[0].get("name"),
                album=(track.get("album") or {}).get("name"),
                external_id=track.get("uri"),
            )
        )
    return sorted(records, key=lambda r: r.played_at)

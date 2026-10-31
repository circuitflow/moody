from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from moody.analysis.analyzer import FakeAnalyzer
from moody.api.app import create_app
from moody.config import Settings
from moody.jobs.scan import run_scan
from moody.store.models import ExternalId, OAuthToken, Track
from tests.audio import write_tone
from tests.fake_spotify import FakeSpotify, track_item


@pytest.fixture
def fake() -> FakeSpotify:
    return FakeSpotify()


def make_client(
    engine: Engine, fake: FakeSpotify, tmp_path: Path, client_id: str | None = "cid"
) -> TestClient:
    settings = Settings(data_dir=tmp_path / "data", spotify_client_id=client_id)
    http = httpx2.Client(transport=fake.transport())
    return TestClient(create_app(settings=settings, engine=engine, http=http))


@pytest.fixture
def client(engine: Engine, fake: FakeSpotify, tmp_path: Path) -> Iterator[TestClient]:
    with make_client(engine, fake, tmp_path) as c:
        yield c


def connect(
    client: TestClient, fake: FakeSpotify, return_to: str = "/#/playlists"
) -> httpx2.Response:
    resp = client.get(
        "/api/auth/spotify/login", params={"return_to": return_to}, follow_redirects=False
    )
    assert resp.status_code == 307
    query = parse_qs(urlsplit(resp.headers["location"]).query)
    fake.challenge = query["code_challenge"][0]
    return client.get(
        "/api/auth/spotify/callback",
        params={"code": "good-code", "state": query["state"][0]},
        follow_redirects=False,
    )


def test_sign_in_with_pkce(client: TestClient, fake: FakeSpotify) -> None:
    assert client.get("/api/auth/spotify").json()["connected"] is False
    resp = client.get("/api/auth/spotify/login", follow_redirects=False)
    target = urlsplit(resp.headers["location"])
    assert (target.scheme, target.netloc, target.path) == (
        "https",
        "accounts.spotify.com",
        "/authorize",
    )
    query = parse_qs(target.query)
    assert query["client_id"] == ["cid"]
    assert query["redirect_uri"] == ["http://127.0.0.1:8000/api/auth/spotify/callback"]
    assert query["code_challenge_method"] == ["S256"]
    assert "playlist-modify-private" in query["scope"][0]

    done = connect(client, fake, return_to="/#/playlists/3")
    assert done.status_code == 307 and done.headers["location"] == "/#/playlists/3"
    status = client.get("/api/auth/spotify").json()
    assert status == {
        "configured": True,
        "connected": True,
        "account": "Owen",
        "redirect_uri": "http://127.0.0.1:8000/api/auth/spotify/callback",
        "error": None,
    }
    assert client.delete("/api/auth/spotify").status_code == 204
    assert client.get("/api/auth/spotify").json()["connected"] is False


def test_failed_sign_ins(client: TestClient, fake: FakeSpotify) -> None:
    assert (
        client.get("/api/auth/spotify/callback", params={"state": "nope", "code": "x"}).status_code
        == 400
    )
    # The user cancels on Spotify's page: back to the app, with the reason shown once.
    resp = client.get("/api/auth/spotify/login", follow_redirects=False)
    state = parse_qs(urlsplit(resp.headers["location"]).query)["state"][0]
    back = client.get(
        "/api/auth/spotify/callback",
        params={"state": state, "error": "access_denied"},
        follow_redirects=False,
    )
    assert back.headers["location"] == "/"
    assert "access_denied" in client.get("/api/auth/spotify").json()["error"]
    assert client.get("/api/auth/spotify").json()["error"] is None
    # A state works only once.
    assert (
        client.get(
            "/api/auth/spotify/callback", params={"state": state, "code": "good-code"}
        ).status_code
        == 400
    )
    # A wrong PKCE verifier (challenge mismatch) is refused by Spotify.
    resp = client.get("/api/auth/spotify/login", follow_redirects=False)
    state = parse_qs(urlsplit(resp.headers["location"]).query)["state"][0]
    fake.challenge = "something-else"
    client.get(
        "/api/auth/spotify/callback",
        params={"state": state, "code": "good-code"},
        follow_redirects=False,
    )
    status = client.get("/api/auth/spotify").json()
    assert status["connected"] is False and "Invalid authorization code" in status["error"]


@pytest.mark.parametrize(
    ("return_to", "expected"),
    [
        ("/#/playlists/1", "/#/playlists/1"),
        ("http://localhost:5173/#/path", "http://localhost:5173/#/path"),  # the dev server
        ("http://testserver/#/playlists/2", "http://testserver/#/playlists/2"),  # moody serve --ui
        ("https://evil.example/steal", "/"),
        ("//evil.example/steal", "/"),
        ("javascript:alert(1)", "/"),
    ],
)
def test_sign_in_only_returns_to_this_app(
    client: TestClient, fake: FakeSpotify, return_to: str, expected: str
) -> None:
    assert connect(client, fake, return_to=return_to).headers["location"] == expected


def test_unconfigured(engine: Engine, fake: FakeSpotify, tmp_path: Path) -> None:
    with make_client(engine, fake, tmp_path, client_id=None) as c:
        assert c.get("/api/auth/spotify").json()["configured"] is False
        resp = c.get("/api/auth/spotify/login", follow_redirects=False)
        assert resp.status_code == 503 and "MOODY_SPOTIFY_CLIENT_ID" in resp.text


@pytest.fixture
def playlist_id(
    client: TestClient, tmp_path: Path, sessions: sessionmaker[Session], fake: FakeSpotify
) -> int:
    root = tmp_path / "Music"
    write_tone(root / "a.flac", 300, seconds=2, title="Coded", artist="Band One")
    write_tone(
        root / "b.flac", 350, seconds=2, title="Rain Song (2003 Remaster)", artist="The Weather"
    )
    write_tone(root / "c.flac", 400, seconds=2, title="Unreleased Demo", artist="Nobody")
    run_scan(root, sessions, FakeAnalyzer)
    with sessions() as s:
        s.execute(update(Track).where(Track.title == "Coded").values(isrc="USAAA0000001"))
        s.commit()
        ids = {t.title: t.id for t in s.scalars(select(Track))}
    fake.catalog = [
        track_item(
            "spotify:track:coded", "Coded - Radio Edit", "Someone Else", 2, isrc="USAAA0000001"
        ),
        track_item("spotify:track:rain-live", "Rain Song - Live", "Weather", 9),  # wrong length
        track_item("spotify:track:rain", "Rain Song", "Weather", 2.5),
    ]
    order = [ids["Unreleased Demo"], ids["Rain Song (2003 Remaster)"], ids["Coded"]]
    created = client.post(
        "/api/playlists",
        json={"name": "Night drive", "track_ids": order, "start": [0, 0], "end": [0.1, 0.1]},
    )
    return int(created.json()["id"])


def test_export_matches_by_isrc_then_by_name(
    client: TestClient, fake: FakeSpotify, playlist_id: int, sessions: sessionmaker[Session]
) -> None:
    assert (
        client.post(f"/api/playlists/{playlist_id}/export/spotify").status_code == 409
    )  # not connected
    connect(client, fake)
    resp = client.post(f"/api/playlists/{playlist_id}/export/spotify")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["url"] == "https://open.spotify.com/playlist/pl1"
    assert (body["matched"], body["total"]) == (2, 3)
    assert [t["title"] for t in body["unmatched"]] == ["Unreleased Demo"]
    assert fake.playlists["pl1"] == {
        "name": "Night drive",
        "public": False,
        "uris": ["spotify:track:rain", "spotify:track:coded"],  # playlist order, minus the miss
    }
    assert "isrc:USAAA0000001" in fake.searches
    with sessions() as s:
        found = {(e.external_id, e.matched_by) for e in s.scalars(select(ExternalId))}
    assert found == {("spotify:track:coded", "isrc"), ("spotify:track:rain", "search")}

    # A second export reuses the matches; only the miss is searched again.
    fake.searches.clear()
    assert client.post(f"/api/playlists/{playlist_id}/export/spotify").json()["matched"] == 2
    assert fake.searches == ["track:Unreleased Demo artist:Nobody"]
    assert client.post("/api/playlists/999/export/spotify").status_code == 404


def test_expired_token_is_refreshed(
    client: TestClient, fake: FakeSpotify, playlist_id: int, sessions: sessionmaker[Session]
) -> None:
    connect(client, fake)
    with sessions() as s:
        s.execute(update(OAuthToken).values(expires_at=datetime.now(UTC) - timedelta(minutes=5)))
        s.commit()
    fake.valid_tokens = {"access-2"}  # the old token no longer works
    assert client.post(f"/api/playlists/{playlist_id}/export/spotify").status_code == 200
    assert fake.token_grants[-1] == "refresh_token"
    with sessions() as s:
        token = s.get(OAuthToken, "spotify")
        assert (
            token is not None
            and token.access_token == "access-2"
            and token.refresh_token == "refresh-1"
        )


def test_rejected_token_is_refreshed_once(
    client: TestClient, fake: FakeSpotify, playlist_id: int
) -> None:
    connect(client, fake)
    fake.valid_tokens = {"access-2"}  # revoked early, though not yet expired
    assert client.post(f"/api/playlists/{playlist_id}/export/spotify").status_code == 200
    assert fake.token_grants.count("refresh_token") == 1


def test_revoked_sign_in_disconnects(
    client: TestClient, fake: FakeSpotify, playlist_id: int
) -> None:
    connect(client, fake)
    fake.valid_tokens = set()
    fake.refresh_ok = False
    resp = client.post(f"/api/playlists/{playlist_id}/export/spotify")
    assert resp.status_code == 409 and "connect again" in resp.text
    assert client.get("/api/auth/spotify").json()["connected"] is False


def test_rate_limits_are_waited_out(
    client: TestClient, fake: FakeSpotify, playlist_id: int
) -> None:
    connect(client, fake)
    fake.queued = [httpx2.Response(429, headers={"Retry-After": "0"})]
    assert client.post(f"/api/playlists/{playlist_id}/export/spotify").status_code == 200
    fake.queued = [httpx2.Response(429, headers={"Retry-After": "0"})] * 6
    resp = client.post(f"/api/playlists/{playlist_id}/export/spotify")
    assert resp.status_code == 502 and "rate-limiting" in resp.text


def test_spotify_errors_are_reported(
    client: TestClient, fake: FakeSpotify, playlist_id: int
) -> None:
    connect(client, fake)
    fake.queued = [
        httpx2.Response(
            403, json={"error": {"status": 403, "message": "Active premium subscription required"}}
        )
    ]
    resp = client.post(f"/api/playlists/{playlist_id}/export/spotify")
    assert resp.status_code == 502 and "premium" in resp.text

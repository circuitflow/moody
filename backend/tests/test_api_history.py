from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker
from typer.testing import CliRunner

from moody.analysis.analyzer import FakeAnalyzer
from moody.api.app import create_app
from moody.cli import app as cli
from moody.config import Settings, get_settings
from moody.jobs.scan import run_scan
from moody.store.models import Play
from tests.audio import write_tone
from tests.fake_lastfm import FakeLastfm
from tests.fake_spotify import FakeSpotify, track_item
from tests.test_spotify import connect


class Both:
    """Route requests to the fake Last.fm or the fake Spotify by host."""

    def __init__(self, lastfm: FakeLastfm, spotify: FakeSpotify) -> None:
        self.lastfm, self.spotify = lastfm, spotify

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        if request.url.host == "ws.audioscrobbler.com":
            return self.lastfm(request)
        return self.spotify(request)


@pytest.fixture
def fakes() -> tuple[FakeLastfm, FakeSpotify]:
    return FakeLastfm(), FakeSpotify()


def make(
    engine: Engine, tmp_path: Path, fakes: tuple[FakeLastfm, FakeSpotify], **settings: Any
) -> TestClient:
    config = Settings(data_dir=tmp_path / "data", **settings)
    http = httpx2.Client(transport=httpx2.MockTransport(Both(*fakes)))
    return TestClient(create_app(settings=config, engine=engine, http=http))


@pytest.fixture
def client(
    engine: Engine,
    tmp_path: Path,
    sessions: sessionmaker[Session],
    fakes: tuple[FakeLastfm, FakeSpotify],
) -> Iterator[TestClient]:
    root = tmp_path / "Music"
    write_tone(root / "rain.flac", 300, title="Rain Song", artist="Weather")
    run_scan(root, sessions, FakeAnalyzer)
    with make(
        engine, tmp_path, fakes, lastfm_api_key="key", lastfm_user="owen", spotify_client_id="cid"
    ) as c:
        yield c


UTS = 1_761_912_000  # 2025-10-31 12:00 UTC


def test_lastfm_import_and_summary(
    client: TestClient, fakes: tuple[FakeLastfm, FakeSpotify]
) -> None:
    lastfm, _ = fakes
    lastfm.scrobbles = [(UTS, "Weather", "Rain Song", ""), (UTS + 600, "Other", "Elsewhere", "")]
    summary = client.get("/api/history").json()
    assert (
        summary["plays"] == 0 and summary["lastfm_configured"] and summary["lastfm_user"] == "owen"
    )
    resp = client.post("/api/history/lastfm", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "source": "lastfm",
        "new": 2,
        "duplicates": 0,
        "skipped": 0,
        "more": False,
        "plays": 2,
        "matched": 1,
    }
    summary = client.get("/api/history").json()
    assert summary["sources"] == [
        {
            "source": "lastfm",
            "plays": 2,
            "matched": 1,
            "first": "2025-10-31T12:00:00Z",
            "last": "2025-10-31T12:10:00Z",
        }
    ]
    assert client.post("/api/history/lastfm", json={"user": "nobody"}).status_code == 502


def test_lastfm_needs_a_key_and_a_user(
    engine: Engine, tmp_path: Path, fakes: tuple[FakeLastfm, FakeSpotify]
) -> None:
    with make(engine, tmp_path, fakes) as c:
        assert c.post("/api/history/lastfm", json={"user": "owen"}).status_code == 503
    with make(engine, tmp_path, fakes, lastfm_api_key="key") as c:
        assert c.post("/api/history/lastfm", json={}).status_code == 422


def test_spotify_recent_plays_dedupe_against_lastfm(
    client: TestClient, fakes: tuple[FakeLastfm, FakeSpotify], sessions: sessionmaker[Session]
) -> None:
    lastfm, spotify = fakes
    assert client.post("/api/history/spotify").status_code == 409  # not connected
    connect(client, spotify)
    # Scrobbled at the start of the listen; Spotify stamps the end, 3 minutes later.
    lastfm.scrobbles = [(UTS, "Weather", "Rain Song", "")]
    client.post("/api/history/lastfm", json={})
    item = track_item("spotify:track:rain", "Rain Song", "Weather", 180)
    item["album"] = {"name": "Album"}
    spotify.recently_played = [
        {"track": item, "played_at": "2025-10-31T12:03:00.000Z"},
        {"track": item, "played_at": "2025-10-31T13:03:00.000Z"},  # a second listen an hour later
    ]
    body = client.post("/api/history/spotify").json()
    assert (body["new"], body["duplicates"], body["plays"], body["matched"]) == (1, 1, 2, 2)
    with sessions() as s:
        times = sorted(p.played_at.replace(tzinfo=UTC) for p in s.scalars(select(Play)))
    assert times == [
        datetime(2025, 10, 31, 12, 0, tzinfo=UTC),
        datetime(2025, 10, 31, 13, 0, tzinfo=UTC),
    ]
    assert client.get("/api/history").json()["spotify_connected"] is True


def test_cli_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    monkeypatch.setenv("MOODY_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    try:
        runner = CliRunner()
        assert "No listening history yet" in runner.invoke(cli, ["history", "status"]).output
        export = tmp_path / "Streaming_History_Audio_2025.json"
        export.write_text(
            json.dumps(
                [
                    {
                        "ts": "2025-03-01T12:04:00Z",
                        "ms_played": 240000,
                        "master_metadata_track_name": "Rain Song",
                        "master_metadata_album_artist_name": "Weather",
                        "master_metadata_album_album_name": "A",
                        "spotify_track_uri": "spotify:track:r",
                    }
                ]
            )
        )
        out = runner.invoke(cli, ["history", "spotify-export", str(export)])
        assert out.exit_code == 0, out.output
        assert "spotify-export: 1 new plays" in out.output
        assert "matched to your library: 0 of 1 plays (0%)" in out.output
        status = runner.invoke(cli, ["history", "status"]).output
        assert "spotify-export" in status and "2025-03-01" in status
        missing = runner.invoke(cli, ["history", "lastfm", "owen"])
        assert missing.exit_code == 2 and "MOODY_LASTFM_API_KEY" in missing.output
    finally:
        get_settings.cache_clear()

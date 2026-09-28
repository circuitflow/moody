from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from moody.analysis.analyzer import FakeAnalyzer
from moody.api.app import create_app
from moody.jobs.scan import run_scan
from moody.legacy.thesis2007 import octant_of
from tests.audio import write_tone


def failing_factory() -> FakeAnalyzer:
    return FakeAnalyzer(fail_on=frozenset({"broken.flac"}))


@pytest.fixture
def client(tmp_path: Path, engine: Engine, sessions: sessionmaker[Session]) -> Iterator[TestClient]:
    root = tmp_path / "Music"
    for i in range(5):
        write_tone(
            root / f"t{i}.flac", 300 + 40 * i, title=f"Song {i}", artist="Band" if i < 3 else "Solo"
        )
    write_tone(root / "broken.flac", 900, title="Broken")
    run_scan(root, sessions, failing_factory)
    with TestClient(create_app(engine=engine)) as c:
        yield c


def test_list_and_paginate(client: TestClient) -> None:
    page = client.get("/api/tracks", params={"limit": 4}).json()
    assert len(page["items"]) == 4 and page["next_cursor"] is not None
    rest = client.get("/api/tracks", params={"limit": 4, "cursor": page["next_cursor"]}).json()
    assert len(rest["items"]) == 2 and rest["next_cursor"] is None
    ids = [t["id"] for t in page["items"] + rest["items"]]
    assert ids == sorted(set(ids))


def test_filters(client: TestClient) -> None:
    assert len(client.get("/api/tracks", params={"q": "solo"}).json()["items"]) == 2
    failed = client.get("/api/tracks", params={"status": "failed"}).json()["items"]
    assert [t["title"] for t in failed] == ["Broken"]
    tagged = client.get("/api/tracks", params={"tag": "energetic"}).json()["items"]
    assert all("energetic" in t["top_tags"] for t in tagged)


def test_track_detail(client: TestClient) -> None:
    first = client.get("/api/tracks", params={"q": "Song 0"}).json()["items"][0]
    detail = client.get(f"/api/tracks/{first['id']}").json()
    assert detail["status"] == "analyzed"
    assert len(detail["segments"]) == 4
    assert detail["thesis_2007"]["octant"] and detail["thesis_2007"]["hevner"]
    assert set(detail["thesis_2007"]["features"]) == {
        "mode",
        "harmony",
        "tempo",
        "rhythm",
        "loudness",
    }
    assert detail["octant"] == octant_of(detail["valence"], detail["arousal"]).label


def test_failed_track_detail_has_error(client: TestClient) -> None:
    broken = client.get("/api/tracks", params={"status": "failed"}).json()["items"][0]
    detail = client.get(f"/api/tracks/{broken['id']}").json()
    assert "fake failure" in detail["error"] and detail["segments"] == []


def test_missing_track_404(client: TestClient) -> None:
    assert client.get("/api/tracks/9999").status_code == 404


def test_map_is_columnar_over_analyzed_tracks(client: TestClient) -> None:
    data = client.get("/api/map").json()
    assert len(data["id"]) == 5  # the failed track has no analysis
    assert {len(v) for v in data.values()} == {5}
    assert all(-1 <= v <= 1 for v in data["valence"])

from collections.abc import Iterator
from pathlib import Path
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from moody.analysis.analyzer import FakeAnalyzer
from moody.api.app import create_app
from moody.jobs.scan import run_scan
from moody.store.models import PlaylistItem
from tests.audio import write_tone


@pytest.fixture
def client(tmp_path: Path, engine: Engine, sessions: sessionmaker[Session]) -> Iterator[TestClient]:
    root = tmp_path / "Music"
    for i in range(4):
        write_tone(root / f"t{i}.flac", 300 + 50 * i, title=f"Song {i}", artist=f"Band {i}")
    write_tone(root / "untitled.flac", 700)  # no tags: the title comes from the file name
    run_scan(root, sessions, FakeAnalyzer)
    with TestClient(create_app(engine=engine)) as c:
        yield c


def ids(client: TestClient) -> list[int]:
    return [int(i) for i in client.get("/api/map").json()["id"]]


def body(track_ids: list[int], **extra: object) -> dict[str, object]:
    return {
        "name": "Distress → Relaxation",
        "track_ids": track_ids,
        "start": [-0.4, 0.4],
        "end": [0.35, -0.35],
        "params": {"search": {"from": "Distress", "to": "Relaxation", "n": 20, "s": 0.5}},
        **extra,
    }


def test_create_get_list_delete(client: TestClient) -> None:
    order = list(reversed(ids(client)))[:3]
    created = client.post("/api/playlists", json=body(order, via=[0.1, 0.2]))
    assert created.status_code == 201
    detail = created.json()
    assert [t["id"] for t in detail["tracks"]] == order  # order kept
    assert detail["count"] == 3 and detail["via"] == [0.1, 0.2]
    assert detail["params"]["search"]["from"] == "Distress"
    assert detail["tracks"][0]["valence"] is not None

    second = client.post("/api/playlists", json=body(order[:1], name="  Short  ")).json()
    assert second["name"] == "Short" and second["via"] is None
    listing = client.get("/api/playlists").json()
    assert [p["id"] for p in listing] == [second["id"], detail["id"]]  # newest first
    assert [p["count"] for p in listing] == [1, 3]

    assert client.get(f"/api/playlists/{detail['id']}").json() == detail
    assert client.delete(f"/api/playlists/{detail['id']}").status_code == 204
    assert client.get(f"/api/playlists/{detail['id']}").status_code == 404
    assert client.delete(f"/api/playlists/{detail['id']}").status_code == 404


def test_deleting_a_playlist_removes_its_items(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    created = client.post("/api/playlists", json=body(ids(client)[:2])).json()
    client.delete(f"/api/playlists/{created['id']}")
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(PlaylistItem)) == 0


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"track_ids": [999_999]}, "unknown track ids: 999999"),
        ({"track_ids": []}, "at least 1"),
        ({"name": "   "}, "blank"),
        ({"start": [0.1]}, "start"),
    ],
)
def test_rejects_bad_playlists(client: TestClient, change: dict[str, object], message: str) -> None:
    resp = client.post("/api/playlists", json={**body(ids(client)[:1]), **change})
    assert resp.status_code == 422
    assert message in resp.text


def test_rejects_repeated_tracks(client: TestClient) -> None:
    first = ids(client)[0]
    resp = client.post("/api/playlists", json=body([first, first]))
    assert resp.status_code == 422 and "distinct" in resp.text


def test_m3u_export(client: TestClient, tmp_path: Path) -> None:
    order = ids(client)
    created = client.post("/api/playlists", json=body(order, name="Late night / calm:\nmix")).json()
    resp = client.get(f"/api/playlists/{created['id']}/m3u")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("audio/x-mpegurl")
    disposition = resp.headers["content-disposition"]
    assert unquote(disposition.split("''", 1)[1]) == "Late night _ calm__mix.m3u8"

    lines = resp.text.splitlines()
    assert lines[:2] == ["#EXTM3U", "#PLAYLIST:Late night / calm: mix"]
    entries = list(zip(lines[2::2], lines[3::2], strict=True))
    assert len(entries) == len(order)
    tracks = created["tracks"]
    for (info, path), track in zip(entries, tracks, strict=True):
        assert Path(path).is_absolute() and Path(path).is_file()
        assert info.startswith("#EXTINF:")
        seconds, label = info.removeprefix("#EXTINF:").split(",", 1)
        assert int(seconds) == round(track["duration_s"])
        if track["artist"]:
            assert label == f"{track['artist']} - {track['title']}"
    assert any(info.endswith(",untitled") for info, _ in entries)  # title from the file name
    assert client.get("/api/playlists/999/m3u").status_code == 404

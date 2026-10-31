import base64
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from moody.analysis.analyzer import FakeAnalyzer
from moody.api import queries
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


def song_id(client: TestClient, title: str) -> int:
    return int(client.get("/api/tracks", params={"q": title}).json()["items"][0]["id"])


def test_meta(client: TestClient) -> None:
    meta = client.get("/api/meta").json()
    assert (meta["tracks"], meta["analyzed"]) == (6, 5)
    assert len(meta["mood_tags"]) == 30 and "christmas" not in meta["mood_tags"]
    assert [o["name"] for o in meta["octants"]][:2] == ["Pleasure", "Excitement"]
    assert {"bpm", "loudness", "tag:happy"} <= set(meta["map_fields"])
    assert meta["audio"] is True


def test_map_has_tags_aligned_with_ids(client: TestClient) -> None:
    data = client.get("/api/map").json()
    assert len(data["tags"]) == len(data["id"]) == len(data["octant_2007"]) == 5
    octants = {"Pleasure", "Excitement", "Arousal", "Distress"}
    octants |= {"Displeasure", "Depression", "Sleepiness", "Relaxation"}
    assert set(data["octant_2007"]) <= octants
    assert all(t.split()[0] == first for t, first in zip(data["tags"], data["tag"], strict=True))


def test_map_values(client: TestClient) -> None:
    ids = client.get("/api/map").json()["id"]
    bpm = client.get("/api/map/values", params={"field": "bpm"}).json()
    assert bpm["field"] == "bpm" and len(bpm["values"]) == len(ids)
    assert all(60 <= v <= 180 for v in bpm["values"])
    energetic = client.get("/api/map/values", params={"field": "tag:energetic"}).json()["values"]
    assert all(0 <= v <= 1 for v in energetic)
    happy = client.get("/api/map/values", params={"field": "tag:happy"}).json()["values"]
    assert happy == [None] * len(ids)  # the fake analyzer never predicts "happy"
    assert client.get("/api/map/values", params={"field": "tag:christmas"}).status_code == 422


def test_neighbors(client: TestClient) -> None:
    target = song_id(client, "Song 0")
    near = client.get(f"/api/tracks/{target}/neighbors", params={"k": 3}).json()
    assert len(near) == 3 and target not in [n["id"] for n in near]
    sims = [n["similarity"] for n in near]
    assert sims == sorted(sims, reverse=True) and all(-1 <= s <= 1 for s in sims)
    assert client.get(f"/api/tracks/{target}/neighbors", params={"k": 50}).json()[-1]["octant"]
    assert client.get("/api/tracks/9999/neighbors").status_code == 404
    failed = song_id(client, "Broken")  # no analysis, no embedding
    assert client.get(f"/api/tracks/{failed}/neighbors").json() == []


def test_neighbor_index_refreshes_after_new_analyses(
    client: TestClient, tmp_path: Path, sessions: sessionmaker[Session]
) -> None:
    target = song_id(client, "Song 0")
    assert len(client.get(f"/api/tracks/{target}/neighbors", params={"k": 50}).json()) == 4
    write_tone(tmp_path / "Music" / "new.flac", 1234, title="New")
    run_scan(tmp_path / "Music", sessions, failing_factory)
    assert len(client.get(f"/api/tracks/{target}/neighbors", params={"k": 50}).json()) == 5


def test_audio_full_and_range(client: TestClient, tmp_path: Path) -> None:
    track = song_id(client, "Song 1")
    size = (tmp_path / "Music" / "t1.flac").stat().st_size
    full = client.get(f"/api/audio/{track}")
    assert full.status_code == 200 and full.headers["content-type"] == "audio/flac"
    assert len(full.content) == size
    part = client.get(f"/api/audio/{track}", headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.content) == 100
    assert part.headers["content-range"] == f"bytes 0-99/{size}"


def test_audio_missing(client: TestClient, tmp_path: Path) -> None:
    track = song_id(client, "Song 2")
    (tmp_path / "Music" / "t2.flac").unlink()
    assert client.get(f"/api/audio/{track}").status_code == 404
    assert client.get("/api/audio/9999").status_code == 404


def _decode(payload: dict) -> np.ndarray:  # type: ignore[type-arg]
    raw = base64.b64decode(payload["vectors"])
    return np.frombuffer(raw, dtype="<f4").reshape(len(payload["id"]), payload["dims"])


def test_embeddings_align_with_the_map(client: TestClient) -> None:
    payload = client.get("/api/embeddings").json()
    assert payload["id"] == client.get("/api/map").json()["id"]  # failed track excluded
    vectors = _decode(payload)
    assert payload["dims"] == 4  # capped at n - 1 for a 5-track library
    np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)


def test_embedding_cosines_follow_the_full_embeddings() -> None:
    """The PCA projection keeps the neighbor order: nearest in 1280-d stays nearest in 32-d."""
    rng = np.random.default_rng(0)
    centers = rng.normal(size=(4, 1280))
    raw = np.concatenate([c + 0.3 * rng.normal(size=(25, 1280)) for c in centers]) + 5.0
    unit = (raw / np.linalg.norm(raw, axis=1, keepdims=True)).astype(np.float32)
    index = queries.EmbeddingIndex(np.arange(100), unit, (0, None))
    reduced = index.reduced(32)
    assert reduced.shape == (100, 32)
    same = reduced[0] @ reduced[1:25].T  # same cluster as track 0
    other = reduced[0] @ reduced[25:].T
    assert same.min() > other.max()
    # The shared offset makes raw cosines bunch up near 1; centered ones spread out.
    assert (unit[0] @ unit[25:].T).min() > 0.9 and other.max() < 0.5
    assert index.reduced(32) is reduced  # cached


def test_reduced_embeddings_do_not_depend_on_row_order() -> None:
    """Component signs are fixed, so reordering the library can't flip the projection."""
    rng = np.random.default_rng(1)
    unit = rng.normal(size=(50, 64)).astype(np.float32)
    perm = rng.permutation(50)
    a = queries.EmbeddingIndex(np.arange(50), unit, (0, None)).reduced(8)
    b = queries.EmbeddingIndex(np.arange(50), unit[perm], (0, None)).reduced(8)
    np.testing.assert_allclose(a[perm], b, atol=1e-4)


def test_embeddings_of_an_empty_library(engine: Engine) -> None:
    with TestClient(create_app(engine=engine)) as c:
        assert c.get("/api/embeddings").json() == {"id": [], "dims": 0, "vectors": ""}

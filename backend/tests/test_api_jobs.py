import json
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from moody.analysis.analyzer import FakeAnalyzer
from moody.api.app import create_app
from moody.config import Settings
from moody.store.models import Job
from tests.audio import write_tone


def library(root: Path, n: int = 4) -> Path:
    for i in range(n):
        write_tone(root / f"t{i}.flac", 300 + 40 * i, title=f"Song {i}", artist="Band")
    return root


def make(engine: Engine, tmp_path: Path, **settings: object) -> TestClient:
    config = Settings(data_dir=tmp_path / "data", scan_workers=1, **settings)  # type: ignore[arg-type]
    app = create_app(settings=config, engine=engine)
    app.state.job_poll_s = 0.01
    return TestClient(app)


@pytest.fixture
def client(engine: Engine, tmp_path: Path) -> Iterator[TestClient]:
    with make(engine, tmp_path, library_path=library(tmp_path / "Music"), fake_analyzer=True) as c:
        yield c
        # Never let a scan outlive the app (it would write to a disposed database).
        SlowAnalyzer.gate.set()
        c.app.state.scans.join(10)  # type: ignore[attr-defined]


def test_scan_from_the_api(client: TestClient) -> None:
    assert client.get("/api/meta").json()["can_scan"] is True
    resp = client.post("/api/scan")
    assert resp.status_code == 202
    job = resp.json()
    assert job["status"] == "running" and job["kind"] == "scan"
    client.app.state.scans.join(10)  # type: ignore[attr-defined]
    done = client.get(f"/api/jobs/{job['id']}").json()
    assert (done["status"], done["progress"], done["total"], done["failed"]) == (
        "completed",
        4,
        4,
        0,
    )
    assert done["finished_at"].endswith("Z")
    assert len(client.get("/api/map").json()["id"]) == 4
    assert client.get("/api/jobs").json()[0]["id"] == job["id"]
    assert client.get("/api/jobs/999").status_code == 404


def events(client: TestClient, job_id: int) -> list[dict[str, object]]:
    out = []
    with client.stream("GET", f"/api/jobs/{job_id}/events") as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        for line in resp.iter_lines():
            if line.startswith("data: "):
                out.append(json.loads(line.removeprefix("data: ")))
    return out


class SlowAnalyzer(FakeAnalyzer):
    gate = threading.Event()

    def analyze(self, path: Path):  # type: ignore[no-untyped-def]
        self.gate.wait(5)
        return super().analyze(path)


def test_progress_streams_and_one_scan_at_a_time(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    SlowAnalyzer.gate.clear()
    monkeypatch.setattr("moody.api.jobs.analyzer_factory", lambda settings: SlowAnalyzer)
    job = client.post("/api/scan").json()
    assert client.post("/api/scan").status_code == 409  # still running
    SlowAnalyzer.gate.set()
    stream = events(client, job["id"])
    assert stream[-1]["status"] == "completed" and stream[-1]["progress"] == 4
    assert all(e["status"] == "running" for e in stream[:-1])
    progress = [int(e["progress"]) for e in stream]  # type: ignore[call-overload]
    assert progress == sorted(progress)
    client.app.state.scans.join(10)  # type: ignore[attr-defined]
    assert client.post("/api/scan").status_code == 202  # free again


def test_a_crashing_scan_is_recorded(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("disk unplugged")

    monkeypatch.setattr("moody.jobs.runner.run_scan", boom)
    job = client.post("/api/scan").json()
    client.app.state.scans.join(10)  # type: ignore[attr-defined]
    failed = client.get(f"/api/jobs/{job['id']}").json()
    assert failed["status"] == "failed" and "disk unplugged" in failed["error"]
    assert events(client, job["id"])[-1]["status"] == "failed"


def test_scanning_needs_a_library(engine: Engine, tmp_path: Path) -> None:
    with make(engine, tmp_path, fake_analyzer=True) as c:
        assert c.get("/api/meta").json()["can_scan"] is False
        resp = c.post("/api/scan")
        assert resp.status_code == 503 and "MOODY_LIBRARY_PATH" in resp.text
    with make(engine, tmp_path, library_path=tmp_path, models_dir=tmp_path / "none") as c:
        resp = c.post("/api/scan")
        assert resp.status_code == 503
        assert "models" in resp.text or "analysis extra" in resp.text


def test_jobs_left_running_by_a_crash_are_marked(
    engine: Engine, sessions: sessionmaker[Session], tmp_path: Path
) -> None:
    with sessions() as s:
        s.add(Job(kind="scan", status="running", total=10))
        s.commit()
    with make(engine, tmp_path) as c:
        job = c.get("/api/jobs").json()[0]
    assert job["status"] == "failed" and "interrupted" in job["error"]

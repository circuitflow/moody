from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from typer.testing import CliRunner

from moody.analysis import models
from moody.analysis.analyzer import FakeAnalyzer
from moody.cli import app
from moody.config import get_settings
from moody.jobs.scan import run_scan
from moody.store import Job, Track, from_blob
from tests.audio import write_tone


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "Music"
    for i in range(6):
        write_tone(root / f"album{i % 2}" / f"track{i}.flac", 300 + 50 * i, title=f"T{i}")
    return root


def statuses(sessions: sessionmaker[Session]) -> dict[str, str]:
    with sessions() as s:
        return {t.title or "": t.status for t in s.scalars(select(Track))}


def test_scan_analyzes_everything(library: Path, sessions: sessionmaker[Session]) -> None:
    result = run_scan(library, sessions, FakeAnalyzer)
    assert (result.ingest.added, result.analyzed, result.failed) == (6, 6, 0)
    with sessions() as s:
        track = s.scalars(select(Track).where(Track.title == "T0")).one()
        assert track.status == "analyzed" and track.analysis is not None
        assert track.analysis.pipeline_version == models.pipeline_version()
        assert track.analysis.octant_2007 is not None
        assert len(track.segments) == 4
        assert from_blob(track.embeddings[0].vector).shape == (8,)
        job = s.get(Job, result.job_id)
        assert job is not None and (job.status, job.progress, job.total) == ("completed", 6, 6)


def test_second_scan_does_no_work(library: Path, sessions: sessionmaker[Session]) -> None:
    run_scan(library, sessions, FakeAnalyzer)
    again = run_scan(library, sessions, FakeAnalyzer)
    assert (again.ingest.unchanged, again.analyzed) == (6, 0)


def test_reanalyze_redoes_everything(library: Path, sessions: sessionmaker[Session]) -> None:
    run_scan(library, sessions, FakeAnalyzer)
    assert run_scan(library, sessions, FakeAnalyzer, reanalyze=True).analyzed == 6


def test_pipeline_change_triggers_reanalysis(
    library: Path, sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    run_scan(library, sessions, FakeAnalyzer)
    monkeypatch.setattr(models, "pipeline_version", lambda: "new-version")
    assert run_scan(library, sessions, FakeAnalyzer).analyzed == 6


def failing_factory() -> FakeAnalyzer:
    return FakeAnalyzer(fail_on=frozenset({"track3.flac"}))


def test_failure_is_recorded_and_not_retried(
    library: Path, sessions: sessionmaker[Session]
) -> None:
    result = run_scan(library, sessions, failing_factory)
    assert (result.analyzed, result.failed) == (5, 1)
    assert statuses(sessions)["T3"] == "failed"
    assert run_scan(library, sessions, failing_factory).failed == 0  # not retried by default
    assert run_scan(library, sessions, FakeAnalyzer, reanalyze=True).failed == 0
    assert statuses(sessions)["T3"] == "analyzed"


def test_process_pool(library: Path, sessions: sessionmaker[Session]) -> None:
    result = run_scan(library, sessions, FakeAnalyzer, workers=2, batch_size=2)
    assert result.analyzed == 6
    assert set(statuses(sessions).values()) == {"analyzed"}


def test_interrupt_keeps_finished_work(library: Path, sessions: sessionmaker[Session]) -> None:
    calls = 0

    class Interrupting(FakeAnalyzer):
        def analyze(self, path: Path):  # type: ignore[no-untyped-def]
            nonlocal calls
            calls += 1
            if calls == 4:
                raise KeyboardInterrupt
            return super().analyze(path)

    result = run_scan(library, sessions, Interrupting, batch_size=2)
    assert result.cancelled and result.analyzed == 3
    resumed = run_scan(library, sessions, FakeAnalyzer)
    assert resumed.analyzed == 3


def test_scan_only_touches_given_root(tmp_path: Path, sessions: sessionmaker[Session]) -> None:
    write_tone(tmp_path / "Music" / "a.flac")
    write_tone(tmp_path / "Music2" / "b.flac", 500)
    run_scan(tmp_path / "Music2", sessions, FakeAnalyzer)
    assert run_scan(tmp_path / "Music", sessions, FakeAnalyzer).analyzed == 1


def test_cli_scan_fake(library: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOODY_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    try:
        result = CliRunner().invoke(app, ["scan", str(library), "--fake"])
    finally:
        get_settings.cache_clear()
    assert result.exit_code == 0, result.output
    assert "6 analyzed, 0 failed" in result.output
    assert (tmp_path / "data" / "moody.db").exists()

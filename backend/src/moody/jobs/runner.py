"""Scans started from the web app: one at a time, on a background thread, tracked in ``jobs``."""

from __future__ import annotations

import logging
import threading
from functools import partial
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from moody.config import Settings
from moody.jobs.scan import AnalyzerFactory, run_scan
from moody.store.models import Job, utcnow

log = logging.getLogger(__name__)


class ScanBusy(RuntimeError):
    pass


class ScanUnavailable(RuntimeError):
    pass


def analyzer_factory(settings: Settings) -> AnalyzerFactory:
    """The analyzer the server scans with; raises ``ScanUnavailable`` with the fix if it can't."""
    if settings.fake_analyzer:
        from moody.analysis.analyzer import FakeAnalyzer

        return FakeAnalyzer
    try:
        from moody.analysis import models
        from moody.analysis.essentia_backend import EssentiaAnalyzer
    except ImportError as exc:  # pragma: no cover - depends on the analysis extra
        raise ScanUnavailable("install the analysis extra: uv sync --extra analysis") from exc
    missing = [name for name, ok in models.status(settings.models_dir).items() if not ok]
    if missing:
        raise ScanUnavailable("models missing: run `moody models pull` first")
    return partial(EssentiaAnalyzer, settings.models_dir)


def mark_interrupted(sessions: sessionmaker[Session]) -> None:
    """Jobs still "running" from a previous server process will never finish."""
    with sessions() as session:
        session.execute(
            update(Job)
            .where(Job.status == "running")
            .values(status="failed", error="interrupted: the server stopped", finished_at=utcnow())
        )
        session.commit()


class ScanRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        sessions: sessionmaker[Session],
        root: Path,
        factory: AnalyzerFactory,
        workers: int = 1,
    ) -> int:
        with self._lock:
            if self.busy():
                raise ScanBusy("a scan is already running")
            with sessions() as session:
                job = Job(kind="scan", status="running", total=0)
                session.add(job)
                session.commit()
                job_id = job.id
            self._thread = threading.Thread(
                target=self._run,
                args=(sessions, root, factory, workers, job_id),
                name=f"scan-{job_id}",
                daemon=True,
            )
            self._thread.start()
            return job_id

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    @staticmethod
    def _run(
        sessions: sessionmaker[Session],
        root: Path,
        factory: AnalyzerFactory,
        workers: int,
        job_id: int,
    ) -> None:
        try:
            run_scan(root, sessions, factory, workers=workers, batch_size=5, job_id=job_id)
        except Exception as exc:  # recorded on the job; the server keeps running
            log.exception("scan %s failed", job_id)
            with sessions() as session:
                job = session.get(Job, job_id)
                if job is not None and job.status == "running":
                    job.status, job.error, job.finished_at = "failed", repr(exc), utcnow()
                    session.commit()

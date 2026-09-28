"""Scan = ingest a library, then analyze every track that is new or stale.

Analysis runs in a process pool (one analyzer per worker, since models load once per process)
and results are written from the main process in batches, so an interrupted scan leaves a
consistent database and simply resumes on the next run.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from moody.analysis import models
from moody.analysis.analyzer import Analyzer, TrackAnalysis
from moody.ingest import IngestReport, ingest
from moody.store.db import to_blob
from moody.store.models import Analysis, Embedding, Job, Segment, Track, utcnow

log = logging.getLogger(__name__)

AnalyzerFactory = Callable[[], Analyzer]
Outcome = tuple[int, TrackAnalysis | None, str | None]  # (track_id, result, error)
ProgressFn = Callable[[int, int], None]


@dataclass
class ScanResult:
    job_id: int
    ingest: IngestReport
    analyzed: int = 0
    failed: int = 0
    cancelled: bool = False
    errors: dict[str, str] = field(default_factory=dict)


def tracks_to_analyze(
    session: Session, root: Path, version: str, reanalyze: bool = False
) -> list[tuple[int, str]]:
    """(id, path) of tracks under ``root`` with no analysis or a stale one. Failed tracks are
    retried only with ``reanalyze``."""
    prefix = str(root.resolve()).rstrip(os.sep) + os.sep
    query = select(Track.id, Track.path).where(Track.path.startswith(prefix, autoescape=True))
    if not reanalyze:
        stale = Track.analysis.has(Analysis.pipeline_version != version)
        query = query.where(Track.status != "failed").where(or_(~Track.analysis.has(), stale))
    return [(tid, path) for tid, path in session.execute(query.order_by(Track.id))]


def apply_analysis(session: Session, track: Track, result: TrackAnalysis, version: str) -> None:
    """Store an analysis for ``track``, replacing any previous one."""
    track.segments.clear()
    track.embeddings.clear()
    session.flush()
    analysis = track.analysis or Analysis(track_id=track.id)
    analysis.pipeline_version = version
    analysis.valence, analysis.arousal = result.valence, result.arousal
    analysis.bpm, analysis.key, analysis.scale = result.bpm, result.key, result.scale
    analysis.loudness_lufs = result.loudness_lufs
    analysis.mood_probs, analysis.tag_probs = result.mood_probs, result.tag_probs
    analysis.top_tags = " ".join(result.top_tags)
    analysis.features_2007 = vars(result.features_2007) if result.features_2007 else None
    verdict = result.verdict_2007
    analysis.octant_2007, analysis.hevner_2007 = verdict if verdict else (None, None)
    analysis.analyzed_at = utcnow()
    track.analysis = analysis
    track.segments.extend(
        Segment(idx=i, start_s=start, valence=v, arousal=a)
        for i, (start, v, a) in enumerate(result.segments)
    )
    track.embeddings.extend(
        Embedding(model=name, dim=int(vec.shape[0]), vector=to_blob(vec))
        for name, vec in result.embeddings.items()
    )
    track.status, track.error = "analyzed", None


# --- worker side -----------------------------------------------------------------------

_worker_analyzer: Analyzer | None = None


def _init_worker(factory: AnalyzerFactory) -> None:
    global _worker_analyzer
    _worker_analyzer = factory()


def _analyze_one(analyzer: Analyzer, track_id: int, path: str) -> Outcome:
    try:
        return track_id, analyzer.analyze(Path(path)), None
    except Exception as exc:  # any per-file failure is recorded, never fatal to the scan
        return track_id, None, f"{type(exc).__name__}: {exc}"


def _analyze_in_worker(track_id: int, path: str) -> Outcome:
    assert _worker_analyzer is not None, "worker not initialized"
    return _analyze_one(_worker_analyzer, track_id, path)


def _outcomes(
    todo: list[tuple[int, str]], factory: AnalyzerFactory, workers: int
) -> Iterator[Outcome]:
    if workers <= 1:
        analyzer = factory()
        for track_id, path in todo:
            yield _analyze_one(analyzer, track_id, path)
        return
    # "spawn" keeps TensorFlow out of forked children and matches macOS behaviour.
    ctx = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(workers, ctx, initializer=_init_worker, initargs=(factory,)) as pool:
        pending: set[Future[Outcome]] = set()
        queue = iter(todo)
        try:
            for track_id, path in queue:
                pending.add(pool.submit(_analyze_in_worker, track_id, path))
                if len(pending) >= workers * 2:
                    break
            while pending:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    yield future.result()
                    nxt = next(queue, None)
                    if nxt is not None:
                        pending.add(pool.submit(_analyze_in_worker, *nxt))
        finally:
            for future in pending:
                future.cancel()


# --- main side ---------------------------------------------------------------------------


def run_scan(
    root: Path,
    sessions: sessionmaker[Session],
    factory: AnalyzerFactory,
    *,
    workers: int = 1,
    limit: int | None = None,
    reanalyze: bool = False,
    batch_size: int = 25,
    progress: ProgressFn | None = None,
) -> ScanResult:
    version = models.pipeline_version()
    with sessions() as session:
        report = ingest(root, session, limit=limit)
        todo = tracks_to_analyze(session, root, version, reanalyze)
        if limit is not None:
            todo = todo[:limit]
        job = Job(kind="scan", status="running", total=len(todo))
        session.add(job)
        session.commit()
        result = ScanResult(job_id=job.id, ingest=report)
        if progress:
            progress(0, len(todo))

        buffer: list[Outcome] = []

        def flush() -> None:
            for track_id, analysis, error in buffer:
                track = session.get(Track, track_id)
                if track is None:
                    continue
                if analysis is not None:
                    apply_analysis(session, track, analysis, version)
                    result.analyzed += 1
                else:
                    track.status, track.error = "failed", error
                    result.failed += 1
                    result.errors[track.path] = error or "unknown error"
            buffer.clear()
            job.progress, job.failed = result.analyzed + result.failed, result.failed
            session.commit()

        try:
            for outcome in _outcomes(todo, factory, workers):
                buffer.append(outcome)
                if len(buffer) >= batch_size:
                    flush()
                if progress:
                    progress(result.analyzed + result.failed + len(buffer), len(todo))
            flush()
            job.status = "completed"
        except KeyboardInterrupt:
            flush()
            job.status, result.cancelled = "cancelled", True
        except Exception as exc:
            session.rollback()
            job.status, job.error = "failed", repr(exc)
            raise
        finally:
            job.finished_at = utcnow()
            session.commit()
    return result

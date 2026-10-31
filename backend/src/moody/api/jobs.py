"""Scanning from the web app: start a scan of the configured library and follow its progress."""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from moody.api.deps import SessionDep
from moody.api.schemas import JobOut
from moody.api.spotify import SettingsDep
from moody.jobs.runner import ScanBusy, ScanRunner, ScanUnavailable, analyzer_factory
from moody.store.models import Job

router = APIRouter(prefix="/api", tags=["jobs"])
POLL_S = 0.5


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt  # SQLite drops the zone


def job_out(job: Job) -> JobOut:
    return JobOut(
        id=job.id,
        kind=job.kind,
        status=job.status,
        progress=job.progress,
        total=job.total,
        failed=job.failed,
        error=job.error,
        created_at=_utc(job.created_at),
        finished_at=_utc(job.finished_at) if job.finished_at else None,
    )


@router.post("/scan", response_model=JobOut, status_code=202)
def start_scan(request: Request, session: SessionDep, settings: SettingsDep) -> JobOut:
    """Scan MOODY_LIBRARY_PATH for new or changed music (409 while a scan runs)."""
    root = settings.library_path
    if root is None or not root.is_dir():
        raise HTTPException(503, "set MOODY_LIBRARY_PATH to your music folder to scan from here")
    try:
        factory = analyzer_factory(settings)
    except ScanUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    runner: ScanRunner = request.app.state.scans
    try:
        job_id = runner.start(request.app.state.sessions, root, factory, settings.scan_workers)
    except ScanBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    job = session.get(Job, job_id)
    assert job is not None
    return job_out(job)


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(session: SessionDep, limit: Annotated[int, Query(ge=1, le=50)] = 5) -> list[JobOut]:
    """The most recent jobs, newest first (the UI resumes showing a running scan)."""
    rows = session.scalars(select(Job).order_by(Job.id.desc()).limit(limit))
    return [job_out(j) for j in rows]


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, session: SessionDep) -> JobOut:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job_out(job)


@router.get(
    "/jobs/{job_id}/events",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "Job updates (SSE)"}},
)
def job_events(job_id: int, request: Request, session: SessionDep) -> StreamingResponse:
    """Server-sent events: the job as JSON whenever it changes, until it finishes."""
    if session.get(Job, job_id) is None:
        raise HTTPException(404, "job not found")
    sessions: sessionmaker[Session] = request.app.state.sessions
    poll: float = getattr(request.app.state, "job_poll_s", POLL_S)

    def events() -> Iterator[str]:
        last = None
        while True:
            with sessions() as s:
                job = s.get(Job, job_id)
                out = job_out(job) if job is not None else None
            if out is None:
                return
            payload = out.model_dump_json()
            if payload != last:
                yield f"event: job\ndata: {payload}\n\n"
                last = payload
            if out.status != "running":
                return
            time.sleep(poll)

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )

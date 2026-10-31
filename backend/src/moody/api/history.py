"""Listening history: coverage, and imports from Last.fm and Spotify (self-hosted only)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx2
from fastapi import APIRouter, HTTPException, Query

from moody.api.deps import SessionDep
from moody.api.queries import summary
from moody.api.schemas import (
    HistoryImport,
    HistoryMood,
    HistorySource,
    HistorySummary,
    LastfmImportRequest,
    MoodBucket,
    TopTrack,
)
from moody.api.spotify import HttpDep, SettingsDep
from moody.store.models import OAuthToken
from moody.streaming import history, imports, spotify
from moody.streaming.history import ImportReport
from moody.streaming.lastfm import LastfmError

router = APIRouter(prefix="/api/history", tags=["history"])

LASTFM_PAGES_PER_REQUEST = 10  # 2,000 scrobbles; the UI calls again while `more` is true


def _summary(session: SessionDep, settings: SettingsDep) -> HistorySummary:
    cov = history.coverage(session)
    return HistorySummary(
        plays=sum(c.plays for c in cov.values()),
        matched=sum(c.matched for c in cov.values()),
        sources=[
            HistorySource(source=k, plays=c.plays, matched=c.matched, first=c.first, last=c.last)
            for k, c in sorted(cov.items())
        ],
        lastfm_configured=bool(settings.lastfm_api_key),
        lastfm_user=settings.lastfm_user,
        spotify_connected=session.get(OAuthToken, spotify.PROVIDER) is not None,
    )


def _result(report: ImportReport, session: SessionDep, settings: SettingsDep) -> HistoryImport:
    summary = _summary(session, settings)
    return HistoryImport(
        source=report.source,
        new=report.new,
        duplicates=report.duplicates,
        skipped=report.skipped,
        more=report.more,
        plays=summary.plays,
        matched=summary.matched,
    )


@router.get("", response_model=HistorySummary)
def get_history(session: SessionDep, settings: SettingsDep) -> HistorySummary:
    return _summary(session, settings)


@router.post("/lastfm", response_model=HistoryImport)
def import_lastfm(
    body: LastfmImportRequest, session: SessionDep, settings: SettingsDep, http: HttpDep
) -> HistoryImport:
    user = (body.user or settings.lastfm_user or "").strip()
    if not settings.lastfm_api_key:
        raise HTTPException(503, "Last.fm isn't set up: set MOODY_LASTFM_API_KEY (see the README)")
    if not user:
        raise HTTPException(422, "a Last.fm user name is needed (or set MOODY_LASTFM_USER)")
    try:
        report = imports.import_lastfm(
            session, http, settings.lastfm_api_key, user, max_pages=LASTFM_PAGES_PER_REQUEST
        )
    except LastfmError as exc:
        raise HTTPException(502, f"Last.fm: {exc}") from exc
    except httpx2.HTTPError as exc:
        raise HTTPException(502, f"Last.fm unreachable: {exc}") from exc
    return _result(report, session, settings)


@router.post("/spotify", response_model=HistoryImport)
def import_spotify(session: SessionDep, settings: SettingsDep, http: HttpDep) -> HistoryImport:
    if not settings.spotify_client_id:
        raise HTTPException(503, "Spotify isn't set up: set MOODY_SPOTIFY_CLIENT_ID")
    client = spotify.SpotifyClient(session, http, settings.spotify_client_id)
    try:
        report = imports.import_spotify_recent(session, client)
    except spotify.NotConnected as exc:
        raise HTTPException(409, str(exc)) from exc
    except spotify.SpotifyError as exc:
        raise HTTPException(502, f"Spotify: {exc}") from exc
    except httpx2.HTTPError as exc:
        raise HTTPException(502, f"Spotify unreachable: {exc}") from exc
    return _result(report, session, settings)


PERIODS = {"all": None, "year": 365, "quarter": 91}
Period = Annotated[str, Query(pattern="^(all|year|quarter)$", description="all, year or quarter")]


def _since(period: str) -> datetime | None:
    days = PERIODS[period]
    return None if days is None else datetime.now(UTC) - timedelta(days=days)


@router.get("/mood", response_model=HistoryMood)
def mood(
    session: SessionDep,
    bucket: Annotated[str, Query(pattern="^(week|hour)$")] = "week",
    tz: Annotated[str, Query(description="IANA time zone for weeks and hours")] = "UTC",
    period: Period = "all",
) -> HistoryMood:
    """Mean mood of what you played, per week or per hour of the day, in your time zone."""
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(422, f"unknown time zone {tz!r}") from exc
    buckets = history.mood_buckets(session, bucket, zone, _since(period))
    return HistoryMood(
        bucket=bucket,
        tz=tz,
        points=[
            MoodBucket(
                key=b.key, plays=b.plays, matched=b.matched, valence=b.valence, arousal=b.arousal
            )
            for b in buckets
        ],
    )


@router.get("/top", response_model=list[TopTrack])
def top(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    period: Period = "all",
) -> list[TopTrack]:
    """Your most-played library tracks."""
    return [
        TopTrack(**summary(track).model_dump(), plays=n)
        for track, n in history.top_tracks(session, limit, _since(period))
    ]

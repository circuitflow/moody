"""Read endpoints over the analyzed library."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from moody.api.deps import SessionDep
from moody.api.schemas import (
    Features2007Out,
    MoodMap,
    SegmentOut,
    TrackDetail,
    TrackPage,
    TrackSummary,
    Verdict2007,
)
from moody.legacy.thesis2007 import octant_of
from moody.store.models import Analysis, Track

router = APIRouter(prefix="/api", tags=["library"])


def _summary_fields(track: Track) -> dict[str, object]:
    a = track.analysis
    return {
        "id": track.id,
        "title": track.title,
        "artist": track.artist,
        "album": track.album,
        "duration_s": track.duration_s,
        "status": track.status,
        "valence": a.valence if a else None,
        "arousal": a.arousal if a else None,
        "octant": octant_of(a.valence, a.arousal).label if a else None,
        "top_tags": a.top_tags.split() if a and a.top_tags else [],
    }


@router.get("/tracks", response_model=TrackPage)
def list_tracks(
    session: SessionDep,
    q: Annotated[str | None, Query(description="Substring of title, artist or album")] = None,
    tag: Annotated[str | None, Query(description="Only tracks with this top tag")] = None,
    status: Annotated[str | None, Query(pattern="^(pending|analyzed|failed)$")] = None,
    cursor: Annotated[int | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> TrackPage:
    query = select(Track).options(selectinload(Track.analysis)).order_by(Track.id)
    if cursor is not None:
        query = query.where(Track.id > cursor)
    if q:
        pattern = f"%{q}%"
        query = query.where(
            or_(Track.title.ilike(pattern), Track.artist.ilike(pattern), Track.album.ilike(pattern))
        )
    if tag:
        query = query.join(Track.analysis).where(
            (" " + Analysis.top_tags + " ").contains(f" {tag} ", autoescape=True)
        )
    if status:
        query = query.where(Track.status == status)
    rows = list(session.scalars(query.limit(limit + 1)))
    items = [TrackSummary.model_validate(_summary_fields(t)) for t in rows[:limit]]
    return TrackPage(items=items, next_cursor=rows[limit - 1].id if len(rows) > limit else None)


@router.get("/tracks/{track_id}", response_model=TrackDetail)
def get_track(track_id: int, session: SessionDep) -> TrackDetail:
    track = session.get(
        Track, track_id, options=[selectinload(Track.analysis), selectinload(Track.segments)]
    )
    if track is None:
        raise HTTPException(404, "track not found")
    detail = TrackDetail.model_validate({**_summary_fields(track), "error": track.error})
    a = track.analysis
    if a is None:
        return detail
    detail.bpm, detail.key, detail.scale = a.bpm, a.key, a.scale
    detail.loudness_lufs, detail.pipeline_version = a.loudness_lufs, a.pipeline_version
    detail.mood_probs, detail.tag_probs = a.mood_probs, a.tag_probs
    detail.segments = [
        SegmentOut(start_s=s.start_s, valence=s.valence, arousal=s.arousal) for s in track.segments
    ]
    if a.features_2007 and a.octant_2007 and a.hevner_2007:
        detail.thesis_2007 = Verdict2007(
            octant=a.octant_2007,
            hevner=a.hevner_2007,
            features=Features2007Out.model_validate(a.features_2007),
        )
    return detail


@router.get("/map", response_model=MoodMap)
def mood_map(session: SessionDep) -> MoodMap:
    rows = session.execute(
        select(
            Track.id,
            Analysis.valence,
            Analysis.arousal,
            Analysis.top_tags,
            Track.title,
            Track.artist,
        )
        .join(Track.analysis)
        .order_by(Track.id)
    ).all()
    return MoodMap(
        id=[r.id for r in rows],
        valence=[round(r.valence, 4) for r in rows],
        arousal=[round(r.arousal, 4) for r in rows],
        octant=[octant_of(r.valence, r.arousal).label for r in rows],
        tag=[r.top_tags.split()[0] if r.top_tags else None for r in rows],
        title=[r.title for r in rows],
        artist=[r.artist for r in rows],
    )

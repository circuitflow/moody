"""Read endpoints over the analyzed library (logic lives in ``moody.api.queries``)."""

from __future__ import annotations

import mimetypes
import threading
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from moody.api import queries
from moody.api.deps import SessionDep
from moody.api.schemas import MapValues, Meta, MoodMap, Neighbor, TrackDetail, TrackPage
from moody.store.models import Track

router = APIRouter(prefix="/api", tags=["library"])
_index_lock = threading.Lock()


@router.get("/meta", response_model=Meta)
def meta(session: SessionDep) -> Meta:
    return queries.meta(session, audio=True)


@router.get("/tracks", response_model=TrackPage)
def list_tracks(
    session: SessionDep,
    q: Annotated[str | None, Query(description="Substring of title, artist or album")] = None,
    tag: Annotated[str | None, Query(description="Only tracks with this top tag")] = None,
    status: Annotated[str | None, Query(pattern="^(pending|analyzed|failed)$")] = None,
    cursor: Annotated[int | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> TrackPage:
    return queries.track_page(session, q=q, tag=tag, status=status, cursor=cursor, limit=limit)


@router.get("/tracks/{track_id}", response_model=TrackDetail)
def get_track(track_id: int, session: SessionDep) -> TrackDetail:
    detail = queries.track_detail(session, track_id)
    if detail is None:
        raise HTTPException(404, "track not found")
    return detail


@router.get("/tracks/{track_id}/neighbors", response_model=list[Neighbor])
def get_neighbors(
    track_id: int,
    request: Request,
    session: SessionDep,
    k: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[Neighbor]:
    if session.get(Track, track_id) is None:
        raise HTTPException(404, "track not found")
    state = request.app.state
    signature = queries.EmbeddingIndex.signature_of(session)
    with _index_lock:
        index: queries.EmbeddingIndex | None = getattr(state, "embedding_index", None)
        if index is None or index.signature != signature:
            index = queries.EmbeddingIndex.build(session)
            state.embedding_index = index
    return queries.neighbors(session, index, track_id, k)


@router.get("/map", response_model=MoodMap)
def mood_map(session: SessionDep) -> MoodMap:
    return queries.mood_map(session)


@router.get("/map/values", response_model=MapValues)
def map_values(
    session: SessionDep,
    field: Annotated[str, Query(description="bpm, loudness, or tag:<mood tag> (see /api/meta)")],
) -> MapValues:
    try:
        return queries.map_values(session, field)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get(
    "/audio/{track_id}",
    response_class=FileResponse,
    responses={200: {"content": {"audio/*": {}}, "description": "The track's audio file"}},
)
def audio(track_id: int, session: SessionDep) -> FileResponse:
    """Stream a track's local file (supports HTTP Range). Only paths stored in the library are
    ever served; the client cannot name a path."""
    track = session.get(Track, track_id)
    if track is None:
        raise HTTPException(404, "track not found")
    path = Path(track.path)
    if not path.is_file():
        raise HTTPException(404, "audio file not found")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)

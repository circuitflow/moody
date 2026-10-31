"""Saved playlists (self-hosted only; the static demo shares paths as links instead)."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Response

from moody import playlists
from moody.api.deps import SessionDep
from moody.api.schemas import PlaylistCreate, PlaylistDetail, PlaylistSummary

router = APIRouter(prefix="/api/playlists", tags=["playlists"])


@router.get("", response_model=list[PlaylistSummary])
def list_playlists(session: SessionDep) -> list[PlaylistSummary]:
    return playlists.list_all(session)


@router.post("", response_model=PlaylistDetail, status_code=201)
def create_playlist(body: PlaylistCreate, session: SessionDep) -> PlaylistDetail:
    try:
        return playlists.create(session, body)
    except playlists.UnknownTracks as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/{playlist_id}", response_model=PlaylistDetail)
def get_playlist(playlist_id: int, session: SessionDep) -> PlaylistDetail:
    detail = playlists.get(session, playlist_id)
    if detail is None:
        raise HTTPException(404, "playlist not found")
    return detail


@router.delete("/{playlist_id}", status_code=204)
def delete_playlist(playlist_id: int, session: SessionDep) -> Response:
    if not playlists.delete(session, playlist_id):
        raise HTTPException(404, "playlist not found")
    return Response(status_code=204)


@router.get(
    "/{playlist_id}/m3u",
    response_class=Response,
    responses={200: {"content": {"audio/x-mpegurl": {}}, "description": "M3U8 playlist"}},
)
def playlist_m3u(playlist_id: int, session: SessionDep) -> Response:
    """The playlist as an M3U8 file with absolute paths (Apple Music: File → Library → Import)."""
    result = playlists.to_m3u(session, playlist_id)
    if result is None:
        raise HTTPException(404, "playlist not found")
    filename, text = result
    return Response(
        text,
        media_type="audio/x-mpegurl; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )

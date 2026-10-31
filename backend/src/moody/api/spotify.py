"""Spotify sign-in (PKCE) and playlist export. Self-hosted only."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlsplit

import httpx2
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse

from moody.api.deps import SessionDep
from moody.api.queries import summary
from moody.api.schemas import SpotifyExport, SpotifyStatus
from moody.config import Settings
from moody.store.models import OAuthToken
from moody.streaming import spotify

router = APIRouter(prefix="/api", tags=["spotify"])


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_http(request: Request) -> httpx2.Client:
    http: httpx2.Client = request.app.state.http
    return http


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
HttpDep = Annotated[httpx2.Client, Depends(get_http)]


def _client_id(settings: Settings) -> str:
    if not settings.spotify_client_id:
        raise HTTPException(
            503, "Spotify isn't set up: set MOODY_SPOTIFY_CLIENT_ID (see the README)"
        )
    return settings.spotify_client_id


def _safe_return(return_to: str | None, settings: Settings, own_origin: str) -> str:
    """Only send the browser back to this app (a relative path or this server's origin) or a
    configured UI origin such as the dev server."""
    if not return_to:
        return "/"
    parts = urlsplit(return_to)
    if (
        not parts.scheme
        and not parts.netloc
        and return_to.startswith("/")
        and not return_to.startswith("//")
    ):
        return return_to
    origin = f"{parts.scheme}://{parts.netloc}"
    return return_to if origin == own_origin or origin in settings.cors_origins else "/"


@router.get("/auth/spotify", response_model=SpotifyStatus)
def status(request: Request, session: SessionDep, settings: SettingsDep) -> SpotifyStatus:
    row = session.get(OAuthToken, spotify.PROVIDER)
    error = request.app.state.spotify_error
    request.app.state.spotify_error = None
    return SpotifyStatus(
        configured=bool(settings.spotify_client_id),
        connected=row is not None,
        account=row.account_name if row else None,
        redirect_uri=settings.spotify_redirect_uri if settings.spotify_client_id else None,
        error=error,
    )


@router.get("/auth/spotify/login", response_class=RedirectResponse, status_code=307)
def login(
    request: Request,
    settings: SettingsDep,
    return_to: Annotated[str | None, Query(description="Where to go after signing in")] = None,
) -> RedirectResponse:
    client_id = _client_id(settings)
    verifier, challenge = spotify.pkce_pair()
    pending: spotify.PendingLogins = request.app.state.spotify_logins
    own_origin = f"{request.url.scheme}://{request.url.netloc}"
    state = pending.add(verifier, _safe_return(return_to, settings, own_origin))
    return RedirectResponse(
        spotify.authorize_url(client_id, settings.spotify_redirect_uri, state, challenge),
        status_code=307,
    )


@router.get("/auth/spotify/callback", response_class=RedirectResponse, status_code=307)
def callback(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    http: HttpDep,
    state: str = "",
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    pending: spotify.PendingLogins = request.app.state.spotify_logins
    entry = pending.pop(state)
    if entry is None:
        raise HTTPException(400, "unknown or expired sign-in; start again from Moody")
    verifier, return_to = entry
    if error or not code:
        request.app.state.spotify_error = (
            f"Spotify sign-in was not completed ({error or 'no code'})"
        )
    else:
        try:
            spotify.exchange_code(
                session,
                http,
                client_id=_client_id(settings),
                redirect_uri=settings.spotify_redirect_uri,
                code=code,
                verifier=verifier,
            )
        except (spotify.SpotifyError, httpx2.HTTPError) as exc:
            request.app.state.spotify_error = str(exc)
    return RedirectResponse(return_to, status_code=307)


@router.delete("/auth/spotify", status_code=204)
def disconnect(session: SessionDep) -> Response:
    spotify.disconnect(session)
    return Response(status_code=204)


@router.post("/playlists/{playlist_id}/export/spotify", response_model=SpotifyExport)
def export_to_spotify(
    playlist_id: int, session: SessionDep, settings: SettingsDep, http: HttpDep
) -> SpotifyExport:
    client = spotify.SpotifyClient(session, http, _client_id(settings))
    try:
        result = spotify.export_playlist(session, client, playlist_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except spotify.NotConnected as exc:
        raise HTTPException(409, str(exc)) from exc
    except spotify.SpotifyError as exc:
        raise HTTPException(502, f"Spotify: {exc}") from exc
    except httpx2.HTTPError as exc:
        raise HTTPException(502, f"Spotify unreachable: {exc}") from exc
    total = result.matched + len(result.unmatched)
    return SpotifyExport(
        url=result.url,
        name=result.name,
        matched=result.matched,
        total=total,
        unmatched=[summary(t) for t in result.unmatched],
    )

"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import Engine

from moody import __version__
from moody.api import history, playlists, spotify, tracks
from moody.config import Settings, get_settings
from moody.store import init_db, session_factory
from moody.streaming.spotify import PendingLogins


class Health(BaseModel):
    status: str
    version: str


router = APIRouter(prefix="/api")


@router.get("/health", response_model=Health, tags=["meta"])
def health() -> Health:
    return Health(status="ok", version=__version__)


def create_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
    http: httpx2.Client | None = None,
) -> FastAPI:
    """Build the app. The database is opened (and migrated) at startup unless ``engine`` is
    given; ``http`` (for Spotify and Last.fm) is created unless given."""
    settings = settings or get_settings()
    own_http = http is None
    client = http or httpx2.Client(timeout=20.0)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        own = engine is None
        db = engine or init_db(settings.database_url)
        app.state.sessions = session_factory(db)
        try:
            yield
        finally:
            if own:
                db.dispose()
            if own_http:
                client.close()

    app = FastAPI(title="Moody", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.http = client
    app.state.spotify_logins = PendingLogins()
    app.state.spotify_error = None
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.include_router(tracks.router)
    app.include_router(playlists.router)
    app.include_router(spotify.router)
    app.include_router(history.router)
    if settings.ui_dir is not None:
        # Mounted last so /api routes win; the UI uses hash routes, so "/" is the only page.
        app.mount("/", StaticFiles(directory=settings.ui_dir, html=True), name="ui")
    return app

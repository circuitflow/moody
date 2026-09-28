"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import Engine

from moody import __version__
from moody.api import tracks
from moody.config import Settings, get_settings
from moody.store import init_db, session_factory


class Health(BaseModel):
    status: str
    version: str


router = APIRouter(prefix="/api")


@router.get("/health", response_model=Health, tags=["meta"])
def health() -> Health:
    return Health(status="ok", version=__version__)


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    """Build the app. The database is opened (and migrated) at startup unless ``engine`` is
    given."""
    settings = settings or get_settings()

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

    app = FastAPI(title="Moody", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.include_router(tracks.router)
    return app

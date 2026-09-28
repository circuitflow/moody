"""Alembic environment. The engine is passed in via ``config.attributes['engine']``;
for CLI autogenerate, ``MOODY_DB_URL`` (or the default settings) is used instead."""

import os

from alembic import context
from sqlalchemy import Engine

from moody.store.models import Base

config = context.config
engine: Engine | None = config.attributes.get("engine")
if engine is None:
    from moody.config import get_settings
    from moody.store.db import make_engine

    engine = make_engine(os.environ.get("MOODY_DB_URL", get_settings().database_url))

with engine.begin() as connection:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=True,  # SQLite needs batch mode for ALTER TABLE
    )
    context.run_migrations()

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

with engine.connect() as connection:
    sqlite = connection.dialect.name == "sqlite"
    if sqlite:
        # SQLite alters most things by rebuilding the table (batch mode: copy, drop, rename).
        # With foreign keys on, dropping `tracks` would cascade-delete every analysis, so they
        # are off while migrating (SQLite's documented recipe for schema changes) and the
        # result is checked before commit. The pragma only takes effect outside a transaction.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
    try:
        with connection.begin():
            context.configure(
                connection=connection,
                target_metadata=Base.metadata,
                render_as_batch=True,  # SQLite needs batch mode for ALTER TABLE
            )
            context.run_migrations()
            if sqlite:
                broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                if broken:
                    raise RuntimeError(f"migration left broken foreign keys: {broken[:5]}")
    finally:
        if sqlite:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()

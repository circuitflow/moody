import numpy as np
from sqlalchemy import Engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from moody.store import Analysis, Embedding, Segment, Track, from_blob, to_blob


def test_migration_creates_schema(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names())
    assert {"tracks", "analyses", "segments", "embeddings", "jobs", "alembic_version"} <= tables


def test_track_round_trip_with_analysis(sessions: sessionmaker[Session]) -> None:
    with sessions.begin() as s:
        track = Track(content_hash="abc", path="/music/a.mp3", file_size=1, file_mtime=0.0)
        track.analysis = Analysis(
            pipeline_version="v1",
            valence=0.5,
            arousal=-0.25,
            mood_probs={"happy": 0.9},
            features_2007={"mode": 60.0},
            octant_2007="Relaxation",
        )
        track.segments = [
            Segment(idx=i, start_s=1.5 * i, valence=0.1 * i, arousal=0.0) for i in range(3)
        ]
        track.embeddings = [Embedding(model="m", dim=4, vector=to_blob(np.arange(4.0)))]
        s.add(track)

    with sessions() as s:
        loaded = s.scalars(select(Track)).one()
        assert loaded.analysis is not None
        assert loaded.analysis.mood_probs == {"happy": 0.9}
        assert [seg.start_s for seg in loaded.segments] == [0.0, 1.5, 3.0]
        np.testing.assert_array_equal(from_blob(loaded.embeddings[0].vector), np.arange(4.0))


def test_deleting_track_cascades(sessions: sessionmaker[Session]) -> None:
    with sessions.begin() as s:
        track = Track(content_hash="x", path="p", file_size=1, file_mtime=0.0)
        track.segments = [Segment(idx=0, start_s=0, valence=0, arousal=0)]
        s.add(track)
    with sessions.begin() as s:
        s.delete(s.scalars(select(Track)).one())
    with sessions() as s:
        assert s.scalars(select(Segment)).all() == []


def test_migration_0002_recomputes_top_tags(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import json

    from alembic import command
    from sqlalchemy import text

    from moody.store.db import alembic_config, make_engine

    engine = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    cfg = alembic_config(engine)
    command.upgrade(cfg, "0001")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tracks (id, content_hash, path, file_size, file_mtime, status,"
                " added_at) VALUES (1, 'h', 'p', 1, 0, 'analyzed', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO analyses (track_id, pipeline_version, valence, arousal, mood_probs,"
                " tag_probs, top_tags, analyzed_at) VALUES (1, 'v', 0, 0, '{}', :probs,"
                " 'christmas film', '2026-01-01')"
            ),
            {"probs": json.dumps({"christmas": 0.5, "film": 0.4, "sad": 0.3, "calm": 0.05})},
        )
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT top_tags FROM analyses")).scalar_one() == "sad"
    engine.dispose()


def test_upgrades_never_lose_data(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Seed every table at the first revision, upgrade to head, and nothing may be gone.

    Guards against SQLite "batch" migrations, which rebuild a table (copy, drop, rename): with
    foreign keys on, dropping `tracks` would cascade-delete analyses, segments and embeddings.
    """
    from alembic import command
    from sqlalchemy import text

    from moody.store.db import alembic_config, make_engine

    engine = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    cfg = alembic_config(engine)
    command.upgrade(cfg, "0001")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tracks (id, content_hash, path, file_size, file_mtime, status,"
                " added_at) VALUES (1, 'h', 'p', 1, 0, 'analyzed', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO analyses (track_id, pipeline_version, valence, arousal, mood_probs,"
                " tag_probs, top_tags, analyzed_at) VALUES (1, 'v', 0, 0, '{}', '{}', '',"
                " '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO segments (track_id, idx, start_s, valence, arousal) VALUES (1,0,0,0,0)"
            )
        )
        conn.execute(
            text("INSERT INTO embeddings (track_id, model, dim, vector) VALUES (1, 'm', 1, x'00')")
        )
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        for table in ("tracks", "analyses", "segments", "embeddings"):
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 1, table
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1  # back on after migrating
    engine.dispose()


def test_batch_rebuild_during_migration_keeps_child_rows(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A future batch migration that rebuilds `tracks` must not cascade-delete analyses.

    Runs a throwaway revision through the real migration environment (env.py), which turns
    foreign keys off while migrating.
    """
    import os

    from alembic import command
    from sqlalchemy import text

    from moody.store.db import MIGRATIONS_DIR, alembic_config, make_engine, migrate

    engine = make_engine(f"sqlite:///{tmp_path / 'm.db'}")
    migrate(engine)
    with engine.begin() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        conn.execute(
            text(
                "INSERT INTO tracks (id, content_hash, path, file_size, file_mtime, status,"
                " added_at) VALUES (1, 'h', 'p', 1, 0, 'analyzed', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO analyses (track_id, pipeline_version, valence, arousal, mood_probs,"
                " tag_probs, top_tags, analyzed_at) VALUES (1, 'v', 0, 0, '{}', '{}', '',"
                " '2026-01-01')"
            )
        )

    extra = tmp_path / "versions"
    extra.mkdir()
    (extra / "9999_rebuild.py").write_text(
        "import sqlalchemy as sa\n"
        "from alembic import op\n"
        f"revision = '9999'\ndown_revision = '{head}'\nbranch_labels = None\ndepends_on = None\n"
        "def upgrade():\n"
        "    with op.batch_alter_table('tracks', recreate='always') as batch:\n"
        "        batch.add_column(sa.Column('scratch', sa.Integer(), nullable=True))\n"
        "def downgrade():\n"
        "    pass\n"
    )
    cfg = alembic_config(engine)
    cfg.set_main_option("path_separator", "os")
    cfg.set_main_option(
        "version_locations", os.pathsep.join([str(MIGRATIONS_DIR / "versions"), str(extra)])
    )
    command.upgrade(cfg, "9999")

    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM analyses")).scalar() == 1
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
    engine.dispose()

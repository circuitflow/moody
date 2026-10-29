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

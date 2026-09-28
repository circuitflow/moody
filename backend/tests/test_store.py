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

import json
from pathlib import Path

from pydantic import TypeAdapter
from sqlalchemy.orm import Session, sessionmaker
from typer.testing import CliRunner

from moody.analysis.analyzer import FakeAnalyzer
from moody.api import queries
from moody.api.schemas import Embeddings, MapValues, Meta, MoodMap, Neighbor, TrackDetail
from moody.cli import app
from moody.config import get_settings
from moody.export import export_static, field_filename
from moody.jobs.scan import run_scan
from tests.audio import write_tone


def make_library(root: Path, n: int = 6) -> Path:
    for i in range(n):
        write_tone(root / f"t{i}.flac", 300 + 37 * i, title=f"Song {i}", artist=f"Artist {i % 2}")
    return root


def test_export_round_trips_through_api_schemas(
    tmp_path: Path, sessions: sessionmaker[Session]
) -> None:
    run_scan(make_library(tmp_path / "Music"), sessions, FakeAnalyzer)
    out = tmp_path / "static"
    report = export_static(sessions, out, k=3)
    assert report.tracks == 6

    meta = Meta.model_validate_json((out / "meta.json").read_text())
    assert meta.audio is False and meta.analyzed == 6
    mood_map = MoodMap.model_validate_json((out / "map.json").read_text())
    assert len(mood_map.id) == 6
    embeddings = Embeddings.model_validate_json((out / "embeddings.json").read_text())
    assert embeddings.id == mood_map.id and embeddings.dims == 5
    for field in meta.map_fields:
        values = MapValues.model_validate_json(
            (out / "map-values" / field_filename(field)).read_text()
        )
        assert values.field == field and len(values.values) == 6
    for track_id in mood_map.id:
        detail = TrackDetail.model_validate_json((out / "tracks" / f"{track_id}.json").read_text())
        assert detail.id == track_id and detail.segments
        near = TypeAdapter(list[Neighbor]).validate_json(
            (out / "neighbors" / f"{track_id}.json").read_text()
        )
        assert len(near) == 3 and track_id not in {n.id for n in near}


def test_export_matches_api_payloads(tmp_path: Path, sessions: sessionmaker[Session]) -> None:
    run_scan(make_library(tmp_path / "Music", 3), sessions, FakeAnalyzer)
    out = tmp_path / "static"
    export_static(sessions, out)
    with sessions() as s:
        assert json.loads((out / "map.json").read_text()) == queries.mood_map(s).model_dump()


def test_cli_export_static(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("MOODY_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    try:
        runner = CliRunner()
        lib = make_library(tmp_path / "Music", 4)
        assert runner.invoke(app, ["scan", str(lib), "--fake"]).exit_code == 0
        result = runner.invoke(app, ["export-static", str(tmp_path / "out")])
    finally:
        get_settings.cache_clear()
    assert result.exit_code == 0, result.output
    assert "exported 4 tracks" in result.output
    assert (tmp_path / "out" / "map-values" / "tag-happy.json").exists()

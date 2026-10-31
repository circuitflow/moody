"""Static export: write the library as JSON files the frontend reads in static mode.

Layout (mirrors the API one-to-one, so ``StaticDataSource`` can swap in for ``ApiDataSource``):

    meta.json                  GET /api/meta (audio: false)
    map.json                   GET /api/map
    embeddings.json            GET /api/embeddings
    map-values/<field>.json    GET /api/map/values?field=<field>  (":" in field -> "-")
    tracks/<id>.json           GET /api/tracks/<id>
    neighbors/<id>.json        GET /api/tracks/<id>/neighbors?k=<k>
    credits.json               demo only: every track's attribution and licence

With ``demo`` (the Jamendo demo tracks), each track gets its attribution and a stream URL,
matched by file name (``<jamendo id>.mp3``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from moody.api import queries
from moody.api.schemas import Attribution, Credit, Neighbor
from moody.demo import DemoTrack, jamendo_id_of
from moody.store.models import Analysis, Track

_neighbors_adapter = TypeAdapter(list[Neighbor])
_credits_adapter = TypeAdapter(list[Credit])


def field_filename(field: str) -> str:
    return field.replace(":", "-") + ".json"


@dataclass
class ExportReport:
    tracks: int
    files: int


def _write(path: Path, model: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json())


def export_static(
    sessions: sessionmaker[Session],
    out: Path,
    *,
    k: int = 10,
    demo: Sequence[DemoTrack] | None = None,
) -> ExportReport:
    files = 0
    by_jamendo = {t.jamendo_id: t for t in demo or ()}
    credits: list[Credit] = []
    with sessions() as session:
        _write(out / "meta.json", queries.meta(session, audio=False))
        mood_map = queries.mood_map(session)
        _write(out / "map.json", mood_map)
        files += 2
        for field in queries.MAP_FIELDS:
            _write(out / "map-values" / field_filename(field), queries.map_values(session, field))
            files += 1
        index = queries.EmbeddingIndex.build(session)
        _write(out / "embeddings.json", queries.embeddings(session, index))
        files += 1
        track_ids = list(
            session.scalars(
                select(Analysis.track_id)
                .join(Analysis.track)
                .where(queries.PRIMARY)
                .order_by(Analysis.track_id)
            )
        )
        for track_id in track_ids:
            detail = queries.track_detail(session, track_id)
            assert detail is not None
            path = session.scalar(select(Track.path).where(Track.id == track_id)) or ""
            d = by_jamendo.get(jamendo_id_of(path) or -1)
            if d is not None:
                detail.attribution = Attribution(
                    title=d.title,
                    artist=d.artist,
                    license=d.license_name,
                    license_url=d.license_url,
                    url=d.share_url,
                )
                detail.audio_url = d.audio_url
                credits.append(
                    Credit(id=track_id, audio_url=d.audio_url, **detail.attribution.model_dump())
                )
            _write(out / "tracks" / f"{track_id}.json", detail)
            near = queries.neighbors(session, index, track_id, k)
            (out / "neighbors").mkdir(parents=True, exist_ok=True)
            (out / "neighbors" / f"{track_id}.json").write_bytes(_neighbors_adapter.dump_json(near))
            files += 2
    if demo is not None:
        (out / "credits.json").write_bytes(_credits_adapter.dump_json(credits))
        files += 1
    return ExportReport(tracks=len(track_ids), files=files)

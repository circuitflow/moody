"""Library queries shared by the HTTP API and the static exporter.

Each function takes a SQLAlchemy ``Session`` and returns API schema objects, so the static demo
bundle is guaranteed to have exactly the shapes the API serves.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import numpy.typing as npt
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from moody import __version__
from moody.analysis.analyzer import MOOD_TAGS
from moody.analysis.models import EFFNET, pipeline_version
from moody.api.schemas import (
    Features2007Out,
    MapValues,
    Meta,
    MoodMap,
    Neighbor,
    OctantInfo,
    SegmentOut,
    TrackDetail,
    TrackPage,
    TrackSummary,
    Verdict2007,
)
from moody.legacy.thesis2007 import Octant, octant_of
from moody.store.db import from_blob
from moody.store.models import Analysis, Embedding, Track

SCALAR_FIELDS = ("bpm", "loudness")
MAP_FIELDS = (*SCALAR_FIELDS, *(f"tag:{t}" for t in sorted(MOOD_TAGS)))
NEIGHBOR_MODEL = EFFNET


def summary(track: Track) -> TrackSummary:
    a = track.analysis
    return TrackSummary(
        id=track.id,
        title=track.title,
        artist=track.artist,
        album=track.album,
        duration_s=track.duration_s,
        status=track.status,
        valence=a.valence if a else None,
        arousal=a.arousal if a else None,
        octant=octant_of(a.valence, a.arousal).label if a else None,
        top_tags=a.top_tags.split() if a and a.top_tags else [],
    )


def meta(session: Session, *, audio: bool) -> Meta:
    tracks = session.scalar(select(func.count()).select_from(Track)) or 0
    analyzed = session.scalar(select(func.count()).select_from(Analysis)) or 0
    return Meta(
        version=__version__,
        pipeline_version=pipeline_version(),
        tracks=tracks,
        analyzed=analyzed,
        mood_tags=sorted(MOOD_TAGS),
        octants=[OctantInfo(name=o.label, angle_deg=o.angle_deg) for o in Octant],
        map_fields=list(MAP_FIELDS),
        audio=audio,
    )


def track_page(
    session: Session,
    *,
    q: str | None = None,
    tag: str | None = None,
    status: str | None = None,
    cursor: int | None = None,
    limit: int = 100,
) -> TrackPage:
    query = select(Track).options(selectinload(Track.analysis)).order_by(Track.id)
    if cursor is not None:
        query = query.where(Track.id > cursor)
    if q:
        pattern = f"%{q}%"
        query = query.where(
            or_(Track.title.ilike(pattern), Track.artist.ilike(pattern), Track.album.ilike(pattern))
        )
    if tag:
        query = query.join(Track.analysis).where(
            (" " + Analysis.top_tags + " ").contains(f" {tag} ", autoescape=True)
        )
    if status:
        query = query.where(Track.status == status)
    rows = list(session.scalars(query.limit(limit + 1)))
    return TrackPage(
        items=[summary(t) for t in rows[:limit]],
        next_cursor=rows[limit - 1].id if len(rows) > limit else None,
    )


def track_detail(session: Session, track_id: int) -> TrackDetail | None:
    track = session.get(
        Track, track_id, options=[selectinload(Track.analysis), selectinload(Track.segments)]
    )
    if track is None:
        return None
    detail = TrackDetail(**summary(track).model_dump(), error=track.error)
    a = track.analysis
    if a is None:
        return detail
    detail.bpm, detail.key, detail.scale = a.bpm, a.key, a.scale
    detail.loudness_lufs, detail.pipeline_version = a.loudness_lufs, a.pipeline_version
    detail.mood_probs, detail.tag_probs = a.mood_probs, a.tag_probs
    detail.segments = [
        SegmentOut(start_s=s.start_s, valence=s.valence, arousal=s.arousal) for s in track.segments
    ]
    if a.features_2007 and a.octant_2007 and a.hevner_2007:
        detail.thesis_2007 = Verdict2007(
            octant=a.octant_2007,
            hevner=a.hevner_2007,
            features=Features2007Out.model_validate(a.features_2007),
        )
    return detail


def mood_map(session: Session) -> MoodMap:
    rows = session.execute(
        select(
            Track.id,
            Analysis.valence,
            Analysis.arousal,
            Analysis.top_tags,
            Analysis.octant_2007,
            Track.title,
            Track.artist,
        )
        .join(Track.analysis)
        .order_by(Track.id)
    ).all()
    return MoodMap(
        id=[r.id for r in rows],
        valence=[round(r.valence, 4) for r in rows],
        arousal=[round(r.arousal, 4) for r in rows],
        octant=[octant_of(r.valence, r.arousal).label for r in rows],
        tag=[r.top_tags.split()[0] if r.top_tags else None for r in rows],
        tags=[r.top_tags or "" for r in rows],
        octant_2007=[r.octant_2007 for r in rows],
        title=[r.title for r in rows],
        artist=[r.artist for r in rows],
    )


def map_values(session: Session, field: str) -> MapValues:
    """Values of ``field`` (see ``MAP_FIELDS``) in ``mood_map`` order. Raises ``ValueError``."""
    if field not in MAP_FIELDS:
        raise ValueError(f"unknown field {field!r}; expected one of {', '.join(MAP_FIELDS)}")
    base = select(Track.id).join(Track.analysis).order_by(Track.id)
    values: list[float | None]
    if field == "bpm":
        values = [v for v in session.scalars(base.with_only_columns(Analysis.bpm))]
    elif field == "loudness":
        values = [v for v in session.scalars(base.with_only_columns(Analysis.loudness_lufs))]
    else:
        tag = field.removeprefix("tag:")
        values = [p.get(tag) for p in session.scalars(base.with_only_columns(Analysis.tag_probs))]
    return MapValues(field=field, values=[None if v is None else round(v, 4) for v in values])


@dataclass
class EmbeddingIndex:
    """Unit-normalized embedding matrix for cosine nearest neighbors."""

    ids: npt.NDArray[np.int64]
    matrix: npt.NDArray[np.float32]
    signature: tuple[int, datetime | None]

    @staticmethod
    def signature_of(session: Session) -> tuple[int, datetime | None]:
        row = session.execute(select(func.count(), func.max(Analysis.analyzed_at))).one()
        return int(row[0]), row[1]

    @classmethod
    def build(cls, session: Session, model: str = NEIGHBOR_MODEL) -> EmbeddingIndex:
        rows = session.execute(
            select(Embedding.track_id, Embedding.vector)
            .where(Embedding.model == model)
            .order_by(Embedding.track_id)
        ).all()
        if not rows:
            return cls(
                np.zeros(0, np.int64), np.zeros((0, 0), np.float32), cls.signature_of(session)
            )
        raw = np.stack([from_blob(r.vector) for r in rows])
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        unit = (raw / np.where(norms == 0, 1, norms)).astype(np.float32)
        ids = np.array([r.track_id for r in rows], dtype=np.int64)
        return cls(ids, unit, cls.signature_of(session))

    def nearest(self, track_id: int, k: int) -> list[tuple[int, float]]:
        hits = np.flatnonzero(self.ids == track_id)
        if hits.size == 0:
            return []
        sims = self.matrix @ self.matrix[hits[0]]
        sims[hits[0]] = -np.inf
        order = np.argsort(-sims, kind="stable")[: min(k, len(self.ids) - 1)]
        return [(int(self.ids[i]), float(sims[i])) for i in order]


def neighbors(session: Session, index: EmbeddingIndex, track_id: int, k: int) -> list[Neighbor]:
    pairs = index.nearest(track_id, k)
    if not pairs:
        return []
    tracks = {
        t.id: t
        for t in session.scalars(
            select(Track)
            .options(selectinload(Track.analysis))
            .where(Track.id.in_([tid for tid, _ in pairs]))
        )
    }
    out = []
    for tid, sim in pairs:
        t = tracks.get(tid)
        if t is None or t.analysis is None:
            continue
        a = t.analysis
        out.append(
            Neighbor(
                id=t.id,
                title=t.title,
                artist=t.artist,
                similarity=round(sim, 4),
                valence=a.valence,
                arousal=a.arousal,
                octant=octant_of(a.valence, a.arousal).label,
            )
        )
    return out

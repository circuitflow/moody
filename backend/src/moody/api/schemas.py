"""API response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TrackSummary(BaseModel):
    id: int
    title: str | None
    artist: str | None
    album: str | None
    duration_s: float | None
    status: str
    valence: float | None = None
    arousal: float | None = None
    octant: str | None = Field(None, description="Russell octant of (valence, arousal)")
    top_tags: list[str] = []


class TrackPage(BaseModel):
    items: list[TrackSummary]
    next_cursor: int | None = Field(None, description="Pass as `cursor` to get the next page")


class SegmentOut(BaseModel):
    start_s: float
    valence: float
    arousal: float


class Features2007Out(BaseModel):
    mode: float
    harmony: float
    tempo: float
    rhythm: float
    loudness: float


class Verdict2007(BaseModel):
    octant: str
    hevner: str
    features: Features2007Out


class Alternate(BaseModel):
    """Another file of the same recording (e.g. the MP3 next to a WAV), hidden from the catalog."""

    id: int
    format: str


class TrackDetail(TrackSummary):
    bpm: float | None = None
    key: str | None = None
    scale: str | None = None
    loudness_lufs: float | None = None
    mood_probs: dict[str, float] = {}
    tag_probs: dict[str, float] = {}
    segments: list[SegmentOut] = []
    thesis_2007: Verdict2007 | None = None
    pipeline_version: str | None = None
    error: str | None = None
    duplicate_of: int | None = Field(None, description="Set when this file is a hidden copy")
    alternates: list[Alternate] = []


class MoodMap(BaseModel):
    """Columnar arrays (one entry per analyzed track) to keep large maps compact."""

    id: list[int]
    valence: list[float]
    arousal: list[float]
    octant: list[str]
    tag: list[str | None]
    tags: list[str] = Field(description="Space-separated top mood tags, most probable first")
    octant_2007: list[str | None] = Field(description="Octant from the 2007 thesis model")
    title: list[str | None]
    artist: list[str | None]


class Embeddings(BaseModel):
    """Compact per-track style vectors for the in-browser path planner, aligned with ``MoodMap.id``.

    Discogs-EffNet embeddings, centered and projected onto their top principal components, then
    L2-normalized, so a dot product is a cosine similarity. Tracks without an embedding get zeros.
    """

    id: list[int]
    dims: int
    vectors: str = Field(
        description="Base64 of little-endian float32, row-major: len(id) rows of `dims` values"
    )


class MapValues(BaseModel):
    """One numeric field per map point, aligned with ``MoodMap.id``, for color-by."""

    field: str
    values: list[float | None]


class OctantInfo(BaseModel):
    name: str
    angle_deg: float


class Meta(BaseModel):
    version: str
    pipeline_version: str
    tracks: int
    analyzed: int
    duplicates: int = Field(0, description="Extra copies hidden from the catalog")
    mood_tags: list[str]
    octants: list[OctantInfo]
    map_fields: list[str] = Field(description="Valid `field` values for /api/map/values")
    audio: bool = Field(description="Whether /api/audio serves local files")


class Neighbor(BaseModel):
    id: int
    title: str | None
    artist: str | None
    similarity: float = Field(description="Cosine similarity of Discogs-EffNet embeddings")
    valence: float
    arousal: float
    octant: str


MoodPoint = tuple[float, float]


class PlaylistCreate(BaseModel):
    """A playlist from the path builder: tracks in order, plus how it was made."""

    name: str = Field(min_length=1, max_length=200)
    track_ids: list[int] = Field(min_length=1, max_length=500)
    start: MoodPoint
    end: MoodPoint
    via: MoodPoint | None = None
    params: dict[str, Any] = Field(
        default_factory=dict, description="Path builder settings (URL search, filters)"
    )

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v

    @field_validator("track_ids")
    @classmethod
    def _distinct(cls, v: list[int]) -> list[int]:
        if len(set(v)) != len(v):
            raise ValueError("track_ids must be distinct")
        return v


class PlaylistSummary(BaseModel):
    id: int
    name: str
    created_at: datetime
    count: int
    start: MoodPoint
    end: MoodPoint
    via: MoodPoint | None


class PlaylistDetail(PlaylistSummary):
    params: dict[str, Any]
    tracks: list[TrackSummary]

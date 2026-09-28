"""API response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


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


class MoodMap(BaseModel):
    """Columnar arrays (one entry per analyzed track) to keep large maps compact."""

    id: list[int]
    valence: list[float]
    arousal: list[float]
    octant: list[str]
    tag: list[str | None]
    title: list[str | None]
    artist: list[str | None]

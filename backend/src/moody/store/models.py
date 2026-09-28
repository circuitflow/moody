"""ORM models. See the design spec, section 7."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, LargeBinary, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, dict[str, float]: JSON}  # noqa: RUF012


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    path: Mapped[str] = mapped_column(Text)
    file_size: Mapped[int]
    file_mtime: Mapped[float]
    title: Mapped[str | None] = mapped_column(Text)
    artist: Mapped[str | None] = mapped_column(Text)
    album: Mapped[str | None] = mapped_column(Text)
    duration_s: Mapped[float | None]
    isrc: Mapped[str | None] = mapped_column(String(15))
    mb_recording_id: Mapped[str | None] = mapped_column(String(36))
    # pending | analyzed | failed
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    added_at: Mapped[datetime] = mapped_column(default=utcnow)

    analysis: Mapped[Analysis | None] = relationship(
        back_populates="track", cascade="all, delete-orphan", uselist=False
    )
    segments: Mapped[list[Segment]] = relationship(
        back_populates="track", cascade="all, delete-orphan", order_by="Segment.idx"
    )
    embeddings: Mapped[list[Embedding]] = relationship(
        back_populates="track", cascade="all, delete-orphan"
    )


class Analysis(Base):
    __tablename__ = "analyses"

    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True
    )
    pipeline_version: Mapped[str] = mapped_column(String(32), index=True)
    # Valence/arousal normalized to [-1, 1].
    valence: Mapped[float]
    arousal: Mapped[float]
    bpm: Mapped[float | None]
    key: Mapped[str | None] = mapped_column(String(4))
    scale: Mapped[str | None] = mapped_column(String(8))
    loudness_lufs: Mapped[float | None]
    mood_probs: Mapped[dict[str, float]] = mapped_column(default=dict)
    tag_probs: Mapped[dict[str, float]] = mapped_column(default=dict)
    # Space-separated tags above threshold, most probable first (for cheap filtering).
    top_tags: Mapped[str] = mapped_column(Text, default="")
    features_2007: Mapped[dict[str, float] | None]
    octant_2007: Mapped[str | None] = mapped_column(String(16))
    hevner_2007: Mapped[str | None] = mapped_column(String(16))
    analyzed_at: Mapped[datetime] = mapped_column(default=utcnow)

    track: Mapped[Track] = relationship(back_populates="analysis")


class Segment(Base):
    """Per-patch mood trajectory (MusiCNN patches, 1.5 s hop)."""

    __tablename__ = "segments"

    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True
    )
    idx: Mapped[int] = mapped_column(primary_key=True)
    start_s: Mapped[float]
    valence: Mapped[float]
    arousal: Mapped[float]

    track: Mapped[Track] = relationship(back_populates="segments")


class Embedding(Base):
    """Mean-pooled embedding per track and model, stored as little-endian float32."""

    __tablename__ = "embeddings"

    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(String(32), primary_key=True)
    dim: Mapped[int]
    vector: Mapped[bytes] = mapped_column(LargeBinary)

    track: Mapped[Track] = relationship(back_populates="embeddings")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    # running | completed | failed | cancelled
    status: Mapped[str] = mapped_column(String(16), default="running")
    progress: Mapped[int] = mapped_column(default=0)
    total: Mapped[int] = mapped_column(default=0)
    failed: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None]


Index("ix_analyses_va", Analysis.valence, Analysis.arousal)

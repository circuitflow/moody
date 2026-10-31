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
    # Set when this file is another copy (e.g. MP3 of a WAV) of the track with this id. Such
    # alternates stay in the database but are hidden from the catalog; files are never touched.
    duplicate_of: Mapped[int | None] = mapped_column(
        ForeignKey("tracks.id", ondelete="SET NULL"), index=True
    )

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


class Playlist(Base):
    """A saved mood-path playlist. ``params`` keeps what rebuilds it in the path builder."""

    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    start_valence: Mapped[float]
    start_arousal: Mapped[float]
    end_valence: Mapped[float]
    end_arousal: Mapped[float]
    via_valence: Mapped[float | None]
    via_arousal: Mapped[float | None]
    params: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    items: Mapped[list[PlaylistItem]] = relationship(
        back_populates="playlist", cascade="all, delete-orphan", order_by="PlaylistItem.position"
    )


class PlaylistItem(Base):
    __tablename__ = "playlist_items"

    playlist_id: Mapped[int] = mapped_column(
        ForeignKey("playlists.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), index=True)

    playlist: Mapped[Playlist] = relationship(back_populates="items")
    track: Mapped[Track] = relationship()


class OAuthToken(Base):
    """Tokens for a connected service, stored locally in plaintext (spec section 7)."""

    __tablename__ = "oauth_tokens"

    provider: Mapped[str] = mapped_column(String(16), primary_key=True)
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime]
    scope: Mapped[str] = mapped_column(Text, default="")
    account_id: Mapped[str | None] = mapped_column(Text)
    account_name: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)


class ExternalId(Base):
    """A library track's id on a streaming service (e.g. a Spotify URI), cached after matching."""

    __tablename__ = "external_ids"

    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String(16), primary_key=True)
    external_id: Mapped[str] = mapped_column(Text)
    matched_by: Mapped[str] = mapped_column(String(16))  # isrc | search
    matched_at: Mapped[datetime] = mapped_column(default=utcnow)


class Play(Base):
    """One listen from a history source, matched to a library track when possible."""

    __tablename__ = "plays"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(16), index=True)  # lastfm | spotify | spotify-export
    played_at: Mapped[datetime] = mapped_column(index=True)  # UTC, start of the listen
    artist: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    album: Mapped[str | None] = mapped_column(Text)
    ms_played: Mapped[int | None]
    external_id: Mapped[str | None] = mapped_column(Text)  # e.g. a Spotify URI
    mbid: Mapped[str | None] = mapped_column(String(36))  # MusicBrainz recording id
    track_id: Mapped[int | None] = mapped_column(
        ForeignKey("tracks.id", ondelete="SET NULL"), index=True
    )


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

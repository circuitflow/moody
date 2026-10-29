"""Tag reading via mutagen, normalized across formats."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import mutagen


@dataclass(frozen=True)
class TrackTags:
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    duration_s: float | None = None
    isrc: str | None = None
    mb_recording_id: str | None = None


def _first(tags: Any, *keys: str) -> str | None:
    if tags is None:
        return None
    for key in keys:
        try:
            value = tags.get(key)
        except (KeyError, ValueError):
            continue
        if isinstance(value, list):
            value = value[0] if value else None
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return None


def read_tags(path: Path) -> TrackTags:
    """Read title/artist/album/ISRC/MusicBrainz ID and duration; the title falls back to the
    file name. Raises ``mutagen.MutagenError`` for unreadable files."""
    audio = mutagen.File(path, easy=True)
    if audio is None:
        raise mutagen.MutagenError(f"unrecognized audio format: {path.name}")
    tags = audio.tags
    length = getattr(audio.info, "length", None)
    return TrackTags(
        title=_first(tags, "title", "TIT2") or path.stem,
        artist=_first(tags, "artist", "albumartist", "TPE1"),
        album=_first(tags, "album", "TALB"),
        duration_s=float(length) if length else None,
        isrc=_first(tags, "isrc", "TSRC"),
        mb_recording_id=_first(tags, "musicbrainz_trackid", "musicbrainz_recordingid"),
    )


# Folder names that say nothing about the artist or album.
PLACEHOLDER_FOLDERS = frozenset({"compilations", "unknown artist", "unknown album"})


def folder_fallback(path: Path, root: Path) -> tuple[str | None, str | None]:
    """(artist, album) from an ``Artist/Album/Track`` layout under ``root``, as iTunes and
    Music.app organize libraries. Shallower layouts are ambiguous and give (None, None)."""
    try:
        parts = path.resolve().relative_to(root.resolve()).parts
    except ValueError:
        return None, None
    if len(parts) < 3:
        return None, None

    def clean(name: str) -> str | None:
        name = name.strip()
        return None if not name or name.lower() in PLACEHOLDER_FOLDERS else name

    return clean(parts[-3]), clean(parts[-2])


def with_folder_fallback(tags: TrackTags, path: Path, root: Path) -> TrackTags:
    """Fill a missing artist or album from the folder layout; tags always win."""
    if tags.artist and tags.album:
        return tags
    artist, album = folder_fallback(path, root)
    return replace(tags, artist=tags.artist or artist, album=tags.album or album)

"""Walk a library and upsert tracks, keyed by content hash."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import mutagen
from sqlalchemy import select
from sqlalchemy.orm import Session

from moody.ingest.hashing import content_hash
from moody.ingest.tags import read_tags
from moody.store.models import Track

log = logging.getLogger(__name__)

AUDIO_EXTENSIONS = frozenset({".mp3", ".flac", ".ogg", ".opus", ".m4a", ".mp4", ".wav", ".aiff"})


def iter_audio_files(root: Path) -> Iterator[Path]:
    """Audio files under ``root`` in a stable order, skipping hidden entries and symlinked
    directories (which also avoids symlink loops)."""
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if not name.startswith(".") and Path(name).suffix.lower() in AUDIO_EXTENSIONS:
                yield Path(dirpath) / name


@dataclass
class IngestReport:
    added: int = 0
    moved: int = 0
    modified: int = 0
    unchanged: int = 0
    duplicates: int = 0
    failed: int = 0

    @property
    def seen(self) -> int:
        return (
            self.added + self.moved + self.modified + self.unchanged + self.duplicates + self.failed
        )


def ingest(root: Path, session: Session, limit: int | None = None) -> IngestReport:
    """Index audio files under ``root``. Commits once at the end; the caller owns the session.

    - same path, size and mtime: unchanged (no hashing, so re-scans are cheap)
    - known hash at a path that no longer exists: the file moved, so the path is updated and the
      analysis kept
    - known hash whose original path still exists: a duplicate copy, skipped
    - same path, new content: modified, so the track is reset to pending and its analysis dropped
    """
    report = IngestReport()
    by_path = {t.path: t for t in session.scalars(select(Track))}
    by_hash = {t.content_hash: t for t in by_path.values()}

    for path in iter_audio_files(root):
        if limit is not None and report.seen >= limit:
            break
        key = str(path.resolve())
        try:
            stat = path.stat()
            existing = by_path.get(key)
            if (
                existing is not None
                and existing.file_size == stat.st_size
                and existing.file_mtime == stat.st_mtime
            ):
                report.unchanged += 1
                continue

            digest = content_hash(path)
            same_content = by_hash.get(digest)
            if same_content is not None and same_content is not existing:
                if Path(same_content.path).exists():
                    report.duplicates += 1
                    continue
                del by_path[same_content.path]
                same_content.path, same_content.file_mtime = key, stat.st_mtime
                by_path[key] = same_content
                report.moved += 1
                continue

            tags = read_tags(path)
            if existing is not None:
                del by_hash[existing.content_hash]
                track = existing
                track.analysis = None
                track.segments = []
                track.embeddings = []
                track.status, track.error = "pending", None
                report.modified += 1
            else:
                track = Track(path=key)
                session.add(track)
                report.added += 1
            track.content_hash = digest
            track.file_size, track.file_mtime = stat.st_size, stat.st_mtime
            track.title, track.artist, track.album = tags.title, tags.artist, tags.album
            track.duration_s, track.isrc = tags.duration_s, tags.isrc
            track.mb_recording_id = tags.mb_recording_id
            by_path[key], by_hash[digest] = track, track
        except (OSError, mutagen.MutagenError) as exc:
            log.warning("skipping %s: %s", path, exc)
            report.failed += 1

    session.commit()
    return report

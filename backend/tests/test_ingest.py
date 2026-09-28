import os
import shutil
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from moody.ingest import content_hash, ingest, iter_audio_files, read_tags
from moody.store import Analysis, Track
from tests.audio import write_tone


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "Music"
    write_tone(
        root / "A" / "one.mp3",
        440,
        title="One",
        artist="Artist A",
        album="Alb",
        isrc="USRC17607839",
    )
    write_tone(root / "A" / "two.flac", 550, title="Two", artist="Artist A")
    write_tone(root / "B" / "three.ogg", 660, title="Three", artist="Artist B")
    write_tone(root / "B" / "untagged.wav", 770)
    (root / "B" / "notes.txt").write_text("not audio")
    write_tone(root / ".hidden" / "skip.flac", 880)
    return root


def tracks(sessions: sessionmaker[Session]) -> dict[str, Track]:
    with sessions() as s:
        return {Path(t.path).name: t for t in s.scalars(select(Track))}


def test_iter_audio_files_skips_hidden_and_non_audio(library: Path) -> None:
    names = [p.name for p in iter_audio_files(library)]
    assert names == ["one.mp3", "two.flac", "three.ogg", "untagged.wav"]


def test_read_tags_across_formats(library: Path) -> None:
    one = read_tags(library / "A" / "one.mp3")
    assert (one.title, one.artist, one.album, one.isrc) == (
        "One",
        "Artist A",
        "Alb",
        "USRC17607839",
    )
    assert one.duration_s == pytest.approx(1.0, abs=0.1)
    assert read_tags(library / "B" / "three.ogg").artist == "Artist B"
    assert read_tags(library / "B" / "untagged.wav").title == "untagged"


def test_content_hash_ignores_name_but_not_content(tmp_path: Path) -> None:
    a = write_tone(tmp_path / "a.flac", 440)
    b = tmp_path / "b.flac"
    shutil.copy(a, b)
    c = write_tone(tmp_path / "c.flac", 441)
    assert content_hash(a) == content_hash(b) != content_hash(c)
    assert len(content_hash(a)) == 32


def test_first_scan_adds_everything(library: Path, sessions: sessionmaker[Session]) -> None:
    with sessions() as s:
        report = ingest(library, s)
    assert (report.added, report.failed) == (4, 0)
    assert all(t.status == "pending" for t in tracks(sessions).values())


def test_rescan_is_a_no_op(library: Path, sessions: sessionmaker[Session]) -> None:
    with sessions() as s:
        ingest(library, s)
    with sessions() as s:
        report = ingest(library, s)
    assert (report.unchanged, report.added) == (4, 0)


def test_moved_file_keeps_identity_and_analysis(
    library: Path, sessions: sessionmaker[Session]
) -> None:
    with sessions() as s:
        ingest(library, s)
        one = s.scalars(select(Track).where(Track.title == "One")).one()
        one.analysis = Analysis(pipeline_version="v", valence=0, arousal=0)
        one.status = "analyzed"
        s.commit()
        original_id = one.id
    (library / "C").mkdir()
    (library / "A" / "one.mp3").rename(library / "C" / "renamed.mp3")

    with sessions() as s:
        report = ingest(library, s)
        moved = s.get(Track, original_id)
        assert moved is not None and moved.path.endswith("C/renamed.mp3")
        assert moved.analysis is not None and moved.status == "analyzed"
    assert (report.moved, report.added) == (1, 0)


def test_duplicate_copy_is_skipped(library: Path, sessions: sessionmaker[Session]) -> None:
    shutil.copy(library / "A" / "two.flac", library / "B" / "two-copy.flac")
    with sessions() as s:
        report = ingest(library, s)
    assert (report.added, report.duplicates) == (4, 1)


def test_modified_file_is_reset_to_pending(library: Path, sessions: sessionmaker[Session]) -> None:
    with sessions() as s:
        ingest(library, s)
        three = s.scalars(select(Track).where(Track.title == "Three")).one()
        three.analysis = Analysis(pipeline_version="v", valence=0, arousal=0)
        three.status = "analyzed"
        s.commit()
    path = library / "B" / "three.ogg"
    write_tone(path, 1000, title="Three (remaster)")
    os.utime(path, (1, 1))

    with sessions() as s:
        report = ingest(library, s)
        three = s.scalars(select(Track).where(Track.title == "Three (remaster)")).one()
        assert three.status == "pending" and three.analysis is None
    assert report.modified == 1


def test_corrupt_file_is_skipped_not_fatal(library: Path, sessions: sessionmaker[Session]) -> None:
    (library / "B" / "broken.mp3").write_bytes(b"\x00" * 64)
    with sessions() as s:
        report = ingest(library, s)
    assert (report.added, report.failed) == (4, 1)


def test_limit(library: Path, sessions: sessionmaker[Session]) -> None:
    with sessions() as s:
        assert ingest(library, s, limit=2).added == 2

import hashlib
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker
from typer.testing import CliRunner

from moody.analysis.analyzer import FakeAnalyzer, TrackAnalysis
from moody.analysis.models import EFFNET
from moody.api.app import create_app
from moody.cli import app
from moody.config import get_settings
from moody.ingest.duplicates import normalize_title
from moody.jobs.scan import run_scan
from moody.store import Track
from tests.audio import write_tone


class SameSongAnalyzer(FakeAnalyzer):
    """Embeddings identical for the same song name: a WAV and an MP3 of one recording."""

    def analyze(self, path: Path) -> TrackAnalysis:
        result = super().analyze(path)
        key = normalize_title(path.stem).encode()
        seed = int.from_bytes(hashlib.blake2b(key, digest_size=8).digest())
        vec = np.random.default_rng(seed).standard_normal(8).astype(np.float32)
        return TrackAnalysis(**{**vars(result), "embeddings": {EFFNET: vec}})


class OtherRecordingAnalyzer(FakeAnalyzer):
    """Embeddings differ per folder: same title, different recording (live, remix, cover)."""

    def analyze(self, path: Path) -> TrackAnalysis:
        result = super().analyze(path)
        seed = int.from_bytes(hashlib.blake2b(str(path.parent).encode(), digest_size=8).digest())
        vec = np.random.default_rng(seed).standard_normal(8).astype(np.float32)
        return TrackAnalysis(**{**vars(result), "embeddings": {EFFNET: vec}})


def by_name(sessions: sessionmaker[Session]) -> dict[str, Track]:
    with sessions() as s:
        return {Path(t.path).name: t for t in s.scalars(select(Track))}


@pytest.mark.parametrize(
    ("raw", "key"),
    [
        ("Nature Boy", "nature boy"),
        ("03 Nature Boy", "nature boy"),
        ("1-03 - Nature Boy!", "nature boy"),
        ("Can't Help Falling In Love", "can t help falling in love"),
        ("99 Luftballons", "luftballons"),  # a known casualty of track-number stripping
    ],
)
def test_normalize_title(raw: str, key: str) -> None:
    assert normalize_title(raw) == key


def test_same_folder_wav_and_mp3(tmp_path: Path, sessions: sessionmaker[Session]) -> None:
    folder = tmp_path / "Music" / "Nat King Cole" / "Greatest"
    write_tone(folder / "Nature Boy.wav", 440, seconds=3)
    write_tone(
        folder / "Nature Boy.mp3",
        440,
        seconds=3,
        title="Nature Boy",
        artist="Nat King Cole",
        album="The Greatest Hits",
        isrc="USCA20100001",
    )
    result = run_scan(tmp_path / "Music", sessions, FakeAnalyzer)
    files = by_name(sessions)
    wav, mp3 = files["Nature Boy.wav"], files["Nature Boy.mp3"]
    assert wav.duplicate_of is None and mp3.duplicate_of == wav.id  # lossless kept
    assert (wav.title, wav.artist, wav.album, wav.isrc) == (
        "Nature Boy",
        "Nat King Cole",
        "The Greatest Hits",
        "USCA20100001",
    )  # tags beat the folder-derived album
    assert result.analyzed == 1  # the MP3 copy was never analyzed
    assert result.dedupe is not None and (result.dedupe.groups, result.dedupe.alternates) == (1, 1)


def test_copies_in_different_folders_need_matching_audio(
    tmp_path: Path, sessions: sessionmaker[Session]
) -> None:
    root = tmp_path / "Music"
    write_tone(root / "Loose" / "Nature Boy.wav", 440, seconds=3)
    write_tone(
        root / "Nat King Cole" / "Hits" / "03 Nature Boy.mp3",
        440,
        seconds=3,
        title="Nature Boy",
        artist="Nat King Cole",
    )
    run_scan(root, sessions, SameSongAnalyzer)
    files = by_name(sessions)
    assert files["03 Nature Boy.mp3"].duplicate_of == files["Nature Boy.wav"].id
    assert files["Nature Boy.wav"].artist == "Nat King Cole"


def test_different_recordings_stay_separate(
    tmp_path: Path, sessions: sessionmaker[Session]
) -> None:
    root = tmp_path / "Music"
    write_tone(root / "Studio" / "x" / "Song.wav", 440, seconds=3)
    write_tone(root / "Live" / "y" / "Song.mp3", 440, seconds=3)
    run_scan(root, sessions, OtherRecordingAnalyzer)
    assert all(t.duplicate_of is None for t in by_name(sessions).values())


def test_different_lengths_stay_separate(tmp_path: Path, sessions: sessionmaker[Session]) -> None:
    folder = tmp_path / "Music" / "A" / "B"
    write_tone(folder / "Song.wav", 440, seconds=2)
    write_tone(folder / "Song.mp3", 440, seconds=8)  # e.g. an edit vs the album version
    run_scan(tmp_path / "Music", sessions, FakeAnalyzer)
    assert all(t.duplicate_of is None for t in by_name(sessions).values())


def test_rescan_is_stable(tmp_path: Path, sessions: sessionmaker[Session]) -> None:
    folder = tmp_path / "Music" / "A" / "B"
    write_tone(folder / "Song.wav", 440, seconds=3)
    write_tone(folder / "Song.mp3", 440, seconds=3)
    run_scan(tmp_path / "Music", sessions, FakeAnalyzer)
    again = run_scan(tmp_path / "Music", sessions, FakeAnalyzer)
    assert again.dedupe is not None and again.dedupe.changed == 0 and again.analyzed == 0


def test_copies_are_hidden_from_the_catalog(
    tmp_path: Path, engine: Engine, sessions: sessionmaker[Session]
) -> None:
    root = tmp_path / "Music"
    write_tone(root / "A" / "B" / "Song.wav", 440, seconds=3)
    write_tone(root / "A" / "B" / "Song.mp3", 440, seconds=3)
    for i in range(3):
        write_tone(root / "A" / "B" / f"Other {i}.wav", 300 + 50 * i, seconds=3)
    run_scan(root, sessions, FakeAnalyzer)
    files = by_name(sessions)
    wav, mp3 = files["Song.wav"], files["Song.mp3"]
    with TestClient(create_app(engine=engine)) as client:
        meta = client.get("/api/meta").json()
        assert (meta["tracks"], meta["analyzed"], meta["duplicates"]) == (4, 4, 1)
        assert mp3.id not in client.get("/api/map").json()["id"]
        assert mp3.id not in [t["id"] for t in client.get("/api/tracks").json()["items"]]
        detail = client.get(f"/api/tracks/{wav.id}").json()
        assert detail["alternates"] == [{"id": mp3.id, "format": "MP3"}]
        assert client.get(f"/api/tracks/{mp3.id}").json()["duplicate_of"] == wav.id
        near = client.get(f"/api/tracks/{wav.id}/neighbors", params={"k": 50}).json()
        assert mp3.id not in [n["id"] for n in near] and len(near) == 3


def test_cli_lists_duplicates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOODY_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    try:
        folder = tmp_path / "Music" / "A" / "B"
        write_tone(folder / "Song.wav", 440, seconds=3)
        write_tone(folder / "Song.mp3", 440, seconds=3)
        runner = CliRunner()
        scan = runner.invoke(app, ["scan", str(tmp_path / "Music"), "--fake"])
        listing = runner.invoke(app, ["duplicates"])
    finally:
        get_settings.cache_clear()
    assert "1 songs have extra copies; 1 files hidden" in scan.output
    assert "uses:" in listing.output and "Song.wav" in listing.output
    assert "copy:" in listing.output and "Song.mp3" in listing.output

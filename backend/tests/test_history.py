import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2
import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from moody.analysis.analyzer import FakeAnalyzer
from moody.jobs.scan import run_scan
from moody.store.models import ExternalId, Play, Track
from moody.streaming import history
from moody.streaming.history import PlayRecord
from moody.streaming.imports import import_lastfm
from moody.streaming.lastfm import LastfmError, recent_tracks
from tests.audio import write_tone
from tests.fake_lastfm import FakeLastfm

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def rec(minutes: float, title: str, artist: str | None = "The Weather", **kw: object) -> PlayRecord:
    return PlayRecord(
        source=str(kw.pop("source", "lastfm")),
        played_at=T0 + timedelta(minutes=minutes),
        title=title,
        artist=artist,
        **kw,  # type: ignore[arg-type]
    )


@pytest.fixture
def library(tmp_path: Path, sessions: sessionmaker[Session]) -> dict[str, int]:
    root = tmp_path / "Music"
    write_tone(root / "rain.flac", 300, title="Rain Song (Remastered)", artist="Weather")
    write_tone(root / "sun.flac", 350, title="Sun Song", artist="Weather")
    write_tone(root / "Weather" / "Album" / "03 Fog Song.flac", 400)  # untagged: names from paths
    run_scan(root, sessions, FakeAnalyzer)
    with sessions() as s:
        return {t.title or "": t.id for t in s.scalars(select(Track))}


def test_ingest_matches_and_skips(sessions: sessionmaker[Session], library: dict[str, int]) -> None:
    with sessions() as s:
        report = history.import_records(
            s,
            "lastfm",
            [
                rec(0, "Rain Song"),  # core title + "The" ignored -> matched
                rec(5, "Sun Song - 2011 Remaster", artist="Weather feat. Someone"),
                rec(10, "03 Fog Song"),  # title and artist from the file and folder names
                rec(15, "Unknown Tune", artist="Nobody"),  # not in the library
                rec(20, "Short", ms_played=10_000),  # under 30 s
                rec(25, "   "),
                None,  # e.g. a podcast entry
            ],
        )
        assert (report.new, report.duplicates, report.skipped) == (4, 0, 3)
        plays = {p.title: p.track_id for p in s.scalars(select(Play))}
    assert plays["Rain Song"] == library["Rain Song (Remastered)"]
    assert plays["Sun Song - 2011 Remaster"] == library["Sun Song"]
    assert plays["03 Fog Song"] is not None
    assert plays["Unknown Tune"] is None


def test_a_play_counts_once_across_sources(
    sessions: sessionmaker[Session], library: dict[str, int]
) -> None:
    with sessions() as s:
        history.import_records(s, "lastfm", [rec(0, "Rain Song"), rec(60, "Rain Song")])
        again = history.import_records(
            s,
            "spotify",
            [
                rec(0.4, "Rain Song (Remastered)", artist="Weather", source="spotify"),  # 24 s off
                rec(1, "Rain Song", source="spotify"),  # 60 s later: a new listen
                rec(60, "Rain Song"),  # re-import of the same scrobble
            ],
        )
        assert (again.new, again.duplicates) == (1, 2)
        assert len(list(s.scalars(select(Play)))) == 3


def test_matches_by_mbid_and_spotify_uri(
    sessions: sessionmaker[Session], library: dict[str, int]
) -> None:
    rain, sun = library["Rain Song (Remastered)"], library["Sun Song"]
    with sessions() as s:
        s.execute(update(Track).where(Track.id == rain).values(mb_recording_id="mbid-rain"))
        s.add(
            ExternalId(
                track_id=sun, provider="spotify", external_id="spotify:track:sun", matched_by="isrc"
            )
        )
        s.commit()
        history.import_records(
            s,
            "lastfm",
            [
                rec(0, "Totally Different Title", artist="X", mbid="mbid-rain"),
                rec(5, "Sole Song", artist="Y", external_id="spotify:track:sun", source="spotify"),
            ],
        )
        got = {p.title: p.track_id for p in s.scalars(select(Play))}
    assert got == {"Totally Different Title": rain, "Sole Song": sun}


def test_rematch_after_new_music_and_duplicates(
    tmp_path: Path, sessions: sessionmaker[Session], library: dict[str, int]
) -> None:
    with sessions() as s:
        history.import_records(s, "lastfm", [rec(0, "Moon Song")])
        assert s.scalar(select(Play.track_id)) is None
    write_tone(tmp_path / "Music" / "moon.flac", 500, title="Moon Song", artist="Weather")
    run_scan(tmp_path / "Music", sessions, FakeAnalyzer)
    with sessions() as s:
        assert history.rematch(s) == 1
        moon = s.scalar(select(Play.track_id))
        # The file later turns out to be a copy of another one: its plays move to that one.
        s.execute(update(Track).where(Track.id == moon).values(duplicate_of=library["Sun Song"]))
        s.commit()
        history.rematch(s)
        assert s.scalar(select(Play.track_id)) == library["Sun Song"]


def test_coverage(sessions: sessionmaker[Session], library: dict[str, int]) -> None:
    with sessions() as s:
        history.import_records(s, "lastfm", [rec(0, "Rain Song"), rec(10, "Nope", artist="Z")])
        cov = history.coverage(s)
    assert cov["lastfm"].plays == 2 and cov["lastfm"].matched == 1
    assert cov["lastfm"].first == T0 and cov["lastfm"].last == T0 + timedelta(minutes=10)


def spotify_extended(
    ts: str, title: str | None, ms: int, artist: str = "Weather"
) -> dict[str, object]:
    return {
        "ts": ts,
        "ms_played": ms,
        "master_metadata_track_name": title,
        "master_metadata_album_artist_name": artist if title else None,
        "master_metadata_album_album_name": "Album",
        "spotify_track_uri": f"spotify:track:{title}" if title else None,
        "episode_name": None if title else "A podcast",
    }


def test_reads_spotify_extended_history_zip(
    tmp_path: Path, sessions: sessionmaker[Session], library: dict[str, int]
) -> None:
    archive = tmp_path / "my_spotify_data.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(
            "Spotify Extended Streaming History/Streaming_History_Audio_2025.json",
            json.dumps(
                [
                    spotify_extended("2025-03-01T12:04:00Z", "Rain Song", 240_000),
                    spotify_extended("2025-03-01T12:05:00Z", None, 600_000),  # podcast
                    spotify_extended("2025-03-01T12:06:00Z", "Sun Song", 5_000),  # skipped
                ]
            ),
        )
        zf.writestr("Spotify Extended Streaming History/ReadMeFirst.pdf", b"%PDF")
    with sessions() as s:
        report = history.import_records(s, "spotify-export", history.read_spotify_export(archive))
        assert (report.new, report.skipped) == (1, 2)
        play = s.scalars(select(Play)).one()
    assert history.as_utc(play.played_at) == datetime(
        2025, 3, 1, 12, 0, tzinfo=UTC
    )  # ts minus 4 min
    assert play.track_id == library["Rain Song (Remastered)"]
    assert play.external_id == "spotify:track:Rain Song"


def test_reads_spotify_basic_history_folder(
    tmp_path: Path, sessions: sessionmaker[Session], library: dict[str, int]
) -> None:
    folder = tmp_path / "MyData"
    folder.mkdir()
    (folder / "StreamingHistory_music_0.json").write_text(
        json.dumps(
            [
                {
                    "endTime": "2025-05-02 08:30",
                    "artistName": "Weather",
                    "trackName": "Sun Song",
                    "msPlayed": 180_000,
                }
            ]
        )
    )
    (folder / "Userdata.json").write_text("{}")
    with sessions() as s:
        report = history.import_records(s, "spotify-export", history.read_spotify_export(folder))
        assert report.new == 1
        play = s.scalars(select(Play)).one()
    assert history.as_utc(play.played_at) == datetime(2025, 5, 2, 8, 27, tzinfo=UTC)
    with pytest.raises(FileNotFoundError, match="no Spotify history files"):
        list(history.read_spotify_export(tmp_path / "Music"))


# Last.fm ---------------------------------------------------------------------------------


def lastfm_client(fake: FakeLastfm) -> httpx2.Client:
    return httpx2.Client(transport=fake.transport())


def scrobbles(n: int, start: int = 1_700_000_000) -> list[tuple[int, str, str, str]]:
    return [(start + 300 * i, "Weather", f"Song {i}", "") for i in range(n)]


def test_lastfm_pages_oldest_first_and_skips_now_playing() -> None:
    fake = FakeLastfm(scrobbles=scrobbles(450), now_playing=("Weather", "Live Now"))
    seen: list[tuple[int, int]] = []
    pages = list(
        recent_tracks(
            lastfm_client(fake),
            "key",
            "owen",
            on_page=lambda d, t: seen.append((d, t)),
            sleep=lambda _: None,
        )
    )
    times = [r.played_at for page in pages for r in page]
    assert len(times) == 450 and "Live Now" not in {r.title for p in pages for r in p}
    assert [len(p) for p in pages] == [50, 200, 200]  # pages 3, 2, then 1
    assert max(r.played_at for r in pages[0]) < min(r.played_at for r in pages[-1])
    assert seen[-1] == (3, 3)


def test_lastfm_single_play_page() -> None:
    fake = FakeLastfm(scrobbles=scrobbles(1))
    pages = list(recent_tracks(lastfm_client(fake), "key", "owen", sleep=lambda _: None))
    assert [len(p) for p in pages] == [1]


def test_capped_lastfm_imports_resume_without_gaps(
    sessions: sessionmaker[Session], library: dict[str, int]
) -> None:
    fake = FakeLastfm(scrobbles=scrobbles(950))
    http = lastfm_client(fake)
    with sessions() as s:
        first = import_lastfm(s, http, "key", "owen", max_pages=2)
        assert first.more and first.new == 350  # the oldest two pages: 150 + 200
        second = import_lastfm(s, http, "key", "owen", max_pages=2)
        assert second.more and second.new == 400
        assert "from" in fake.requests[-1] and "to" in fake.requests[-1]
        third = import_lastfm(s, http, "key", "owen", max_pages=2)
        assert not third.more and third.new == 200
        titles = set(s.scalars(select(Play.title)))
    assert titles == {f"Song {i}" for i in range(950)}
    # Later, only new scrobbles are read.
    fake.scrobbles.append((1_700_000_000 + 300 * 2000, "Weather", "Newest", ""))
    with sessions() as s:
        assert import_lastfm(s, http, "key", "owen").new == 1


def test_lastfm_errors() -> None:
    fake = FakeLastfm()
    with pytest.raises(LastfmError, match="User not found"):
        list(recent_tracks(lastfm_client(fake), "key", "nobody", sleep=lambda _: None))
    with pytest.raises(LastfmError, match="Invalid API key"):
        list(recent_tracks(lastfm_client(fake), "wrong", "owen", sleep=lambda _: None))
    fake.queued = [httpx2.Response(200, json={"error": 29, "message": "Rate limit exceeded"})]
    fake.scrobbles = scrobbles(3)
    waits: list[float] = []
    pages = list(recent_tracks(lastfm_client(fake), "key", "owen", sleep=waits.append))
    assert sum(len(p) for p in pages) == 3 and waits  # waited, then carried on

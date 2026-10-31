import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from typer.testing import CliRunner

from moody import demo
from moody.analysis.analyzer import FakeAnalyzer
from moody.api.schemas import Credit, TrackDetail
from moody.cli import app as cli
from moody.config import get_settings
from moody.export import export_static
from moody.jobs.scan import run_scan
from moody.store import init_db, session_factory
from moody.store.models import Analysis, Embedding, Segment, Track
from tests.audio import write_tone

LICENSES = {
    "by": "http://creativecommons.org/licenses/by/3.0/",
    "by-sa": "http://creativecommons.org/licenses/by-sa/4.0/",
    "by-nc": "http://creativecommons.org/licenses/by-nc/3.0/",
    "by-nc-nd": "http://creativecommons.org/licenses/by-nc-nd/3.0/",
}


def split_tsv(path: Path, rows: list[tuple[int, list[str]]]) -> Path:
    lines = ["TRACK_ID\tARTIST_ID\tALBUM_ID\tPATH\tDURATION\tTAGS"]
    for tid, tags in rows:
        cols = [f"track_{tid:07d}", "artist_000001", "album_000001", f"00/{tid}.mp3", "200.0"]
        lines.append("\t".join(cols + [f"mood/theme---{t}" for t in tags]))
    path.write_text("\n".join(lines) + "\n")
    return path


class FakeJamendo:
    """api.jamendo.com/v3.0/tracks plus the audio hosts."""

    def __init__(self, catalog: dict[int, dict[str, Any]], audio: dict[str, bytes]) -> None:
        self.catalog, self.audio = catalog, audio
        self.lookups = 0
        self.fail_audio: dict[str, int] = {}  # url -> failures left

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        if request.url.host == "api.jamendo.com":
            q = parse_qs(urlsplit(str(request.url)).query)
            if q["client_id"] != ["cid"]:
                return httpx2.Response(
                    200,
                    json={"headers": {"status": "failed", "error_message": "Invalid client id"}},
                )
            self.lookups += 1
            ids = [int(i) for i in q["id"][0].split()]
            assert len(ids) <= 100
            results = [self.catalog[i] for i in ids if i in self.catalog]
            return httpx2.Response(200, json={"headers": {"status": "success"}, "results": results})
        url = str(request.url)
        if self.fail_audio.get(url, 0) > 0:
            self.fail_audio[url] -= 1
            return httpx2.Response(503)
        if url in self.audio:
            return httpx2.Response(200, content=self.audio[url])
        return httpx2.Response(404)


def item(tid: int, license: str = "by", duration: int = 200, **kw: Any) -> dict[str, Any]:
    return {
        "id": str(tid),
        "name": f"Song {tid}",
        "artist_name": f"Artist {tid % 7}",
        "album_name": "Album",
        "duration": duration,
        "license_ccurl": LICENSES[license],
        "shareurl": f"https://www.jamendo.com/track/{tid}",
        "audio": f"https://prod-1.storage.jamendo.com/?trackid={tid}&format=mp32",
        **kw,
    }


def test_load_split_and_licences(tmp_path: Path) -> None:
    split = demo.load_split(
        split_tsv(tmp_path / "s.tsv", [(3524, ["melodic"]), (7, ["happy", "film"])])
    )
    assert split[0] == demo.SplitTrack(3524, 200.0, ("melodic",))
    assert split[1].tags == ("happy", "film")
    assert demo.license_kind(LICENSES["by-sa"]) == "by-sa"
    assert demo.license_kind("https://creativecommons.org/licenses/by-nc-nd/3.0/") == "by-nc-nd"
    assert demo.license_kind("http://example.com") is None


def test_eligible_tracks_filters_licence_length_and_availability(tmp_path: Path) -> None:
    rows = [(i, ["happy"]) for i in range(1, 251)]
    catalog = {i: item(i) for i in range(1, 251)}
    catalog[2] = item(2, "by-nc")
    catalog[3] = item(3, "by-nc-nd")
    catalog[4] = item(4, "by-sa")
    catalog[5] = item(5, duration=30)  # too short
    catalog[6] = item(6, duration=900)  # too long
    catalog[7] = item(7, audio="")
    del catalog[8]  # gone from Jamendo
    catalog[9999] = item(9999)  # not in the split: ignored
    fake = FakeJamendo(catalog, {})
    jam = demo.Jamendo(httpx2.Client(transport=httpx2.MockTransport(fake)), "cid")
    found, report = demo.eligible_tracks(jam, demo.load_split(split_tsv(tmp_path / "s.tsv", rows)))
    ids = {t.jamendo_id for t in found}
    assert fake.lookups == 3  # 250 ids in batches of 100
    assert {2, 3, 5, 6, 7, 8, 9999}.isdisjoint(ids) and {1, 4} <= ids
    assert (report.in_split, report.available, report.licensed) == (250, 249, 244)
    assert report.licenses["by-nc"] == 1
    sa = next(t for t in found if t.jamendo_id == 4)
    assert sa.license_name == "CC BY-SA 4.0" and sa.tags == ("happy",)

    bad = demo.Jamendo(httpx2.Client(transport=httpx2.MockTransport(fake)), "nope")
    with pytest.raises(demo.JamendoError, match="Invalid client id"):
        bad.tracks([1])


def track(tid: int, tags: tuple[str, ...]) -> demo.DemoTrack:
    return demo.DemoTrack(tid, f"Song {tid}", "A", "B", 200, LICENSES["by"], "u", f"a{tid}", tags)


def test_stratify_covers_rare_tags_and_is_deterministic() -> None:
    tracks = [track(i, ("happy",)) for i in range(100)]
    tracks += [track(1000 + i, ("dark",)) for i in range(5)]
    tracks += [track(2000, ("space", "happy"))]
    picked = demo.stratify(tracks, 20, seed=1)
    assert len(picked) == 20 and len({t.jamendo_id for t in picked}) == 20
    tags = Counter(tag for t in picked for tag in t.tags)
    assert tags["dark"] == 5 and tags["space"] == 1  # every rare track got in
    assert demo.stratify(tracks, 20, seed=1) == picked
    assert len(demo.stratify(tracks, 10_000)) == len(tracks)


def test_csv_round_trip_and_shards(tmp_path: Path) -> None:
    tracks = [track(i, ("happy", "film")) for i in range(10)]
    demo.write_csv(tracks, tmp_path / "t.csv")
    assert demo.read_csv(tmp_path / "t.csv") == tracks
    parts = [demo.shard(tracks, i, 3) for i in range(3)]
    assert sorted(t.jamendo_id for p in parts for t in p) == list(range(10))
    with pytest.raises(ValueError):
        demo.shard(tracks, 3, 3)


def test_download_is_resumable_and_retries(tmp_path: Path) -> None:
    tracks = [track(i, ()) for i in range(4)]
    for t in tracks:
        t.audio_url = f"http://audio.test/{t.audio_url}"
    fake = FakeJamendo({}, {f"http://audio.test/a{i}": b"ID3" + bytes([i]) * 100 for i in range(3)})
    fake.fail_audio = {"http://audio.test/a1": 2}  # fails twice, then works; a3 doesn't exist
    http = httpx2.Client(transport=httpx2.MockTransport(fake))
    dest = tmp_path / "audio"
    report = demo.download(tracks, dest, http, workers=2, sleep=lambda _: None)
    assert (report.downloaded, report.present, report.failed) == (3, 0, [3])
    assert (dest / "1.mp3").read_bytes() == b"ID3" + bytes([1]) * 100
    assert not list(dest.glob("*.part"))
    again = demo.download(tracks, dest, http, sleep=lambda _: None)
    assert (again.downloaded, again.present) == (0, 3)


def scan_shard(root: Path, data: Path, ids: list[int]) -> Path:
    for i in ids:
        write_tone(root / f"{i}.flac", 200 + 30 * i, title="tagged wrong", artist="?")
    engine = init_db(f"sqlite:///{data / 'moody.db'}")
    run_scan(root, session_factory(engine), FakeAnalyzer)
    engine.dispose()
    return data / "moody.db"


def test_merge_shards_and_export_credits(tmp_path: Path, sessions: sessionmaker[Session]) -> None:
    a = scan_shard(tmp_path / "a", tmp_path / "da", [1, 2, 3])
    b = scan_shard(tmp_path / "b", tmp_path / "db", [4, 5])
    target = sessions.kw["bind"]
    from sqlalchemy import create_engine

    sources = [create_engine(f"sqlite:///{a}"), create_engine(f"sqlite:///{b}")]
    shard_embeddings = 0
    for e in sources:
        with e.connect() as c:
            shard_embeddings += c.scalar(select(func.count()).select_from(Embedding)) or 0
    try:
        assert demo.merge(sources, target) == 5
        assert demo.merge(sources[:1], target) == 0  # same files again: skipped by content hash
    finally:
        for e in sources:
            e.dispose()
    tracks = [track(i, ("happy",)) for i in (1, 2, 3, 4, 5)]
    with sessions() as s:
        assert demo.apply_metadata(s, tracks) == 5
        assert s.scalar(select(func.count()).select_from(Analysis)) == 5
        assert s.scalar(select(func.count()).select_from(Embedding)) == shard_embeddings > 0
        assert s.scalar(select(func.count()).select_from(Segment)) > 5
        titles = sorted(s.scalars(select(Track.title)))
    assert titles == [f"Song {i}" for i in (1, 2, 3, 4, 5)]

    out = tmp_path / "static"
    report = export_static(sessions, out, k=2, demo=tracks)
    credits = [Credit.model_validate(c) for c in json.loads((out / "credits.json").read_text())]
    assert len(credits) == 5 and report.files > 5
    first = TrackDetail.model_validate_json((out / "tracks" / f"{credits[0].id}.json").read_text())
    assert first.attribution is not None and first.attribution.license == "CC BY 3.0"
    assert first.audio_url and first.audio_url.startswith("a")
    plain = tmp_path / "plain"
    export_static(sessions, plain, k=2)
    assert not (plain / "credits.json").exists()


def test_cli_select_needs_a_client_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JAMENDO_CLIENT_ID", raising=False)
    monkeypatch.delenv("MOODY_JAMENDO_CLIENT_ID", raising=False)
    monkeypatch.setenv("MOODY_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    try:
        tsv = split_tsv(tmp_path / "s.tsv", [(1, ["happy"])])
        out = CliRunner().invoke(cli, ["demo", "select", str(tsv), str(tmp_path / "t.csv")])
        plain = re.sub(r"\x1b\[[0-9;]*m", "", out.output)  # Rich colours output on CI
        assert out.exit_code != 0 and "client-id" in plain
    finally:
        get_settings.cache_clear()

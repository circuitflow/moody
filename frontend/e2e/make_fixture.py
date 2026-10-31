"""Build the deterministic static bundle the end-to-end tests run against.

Run from ``backend/``:  uv run python ../frontend/e2e/make_fixture.py ../frontend/public/data

Writes 40 synthetic WAV tracks, scans them with the fake analyzer (deterministic, no models),
and exports them like the public demo: files named by a Jamendo-style id, metadata and credits
from a demo CSV, and "stream" URLs pointing at copies of the WAVs under ``data/audio/``.
"""

from __future__ import annotations

import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

from moody.analysis.analyzer import FakeAnalyzer
from moody.demo import DemoTrack, apply_metadata
from moody.export import export_static
from moody.jobs.scan import run_scan
from moody.store import init_db, session_factory

N_TRACKS = 40
SR = 8000


def write_wav(path: Path, freq: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.arange(SR // 4) / SR
    pcm = (0.2 * np.sin(2 * np.pi * freq * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main(out: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "Music"
        demo = []
        for i in range(N_TRACKS):
            jid = 1000 + i
            write_wav(root / f"{jid}.wav", 110 + 17 * i)
            write_wav(out / "audio" / f"{jid}.wav", 110 + 17 * i)
            license = "by-sa/4.0" if i % 4 == 0 else "by/3.0"
            demo.append(
                DemoTrack(
                    jamendo_id=jid,
                    title=f"Track {i:02d}",
                    artist=f"Artist {i % 6}",
                    album=f"Album {i % 9}",
                    duration_s=0.25,
                    license_url=f"https://creativecommons.org/licenses/{license}/",
                    share_url=f"https://www.jamendo.com/track/{jid}",
                    audio_url=f"data/audio/{jid}.wav",  # relative to the page, like BASE_URL
                    tags=("happy",),
                )
            )
        engine = init_db(f"sqlite:///{Path(tmp) / 'moody.db'}")
        try:
            sessions = session_factory(engine)
            run_scan(root, sessions, FakeAnalyzer)
            with sessions() as session:
                apply_metadata(session, demo)
            report = export_static(sessions, out, demo=demo)
        finally:
            engine.dispose()
    print(f"e2e fixture: {report.tracks} tracks, {report.files} files in {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())

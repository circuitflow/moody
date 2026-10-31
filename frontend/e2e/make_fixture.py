"""Build the deterministic static bundle the end-to-end tests run against.

Run from ``backend/``:  uv run python ../frontend/e2e/make_fixture.py ../frontend/public/data

Writes 40 synthetic WAV tracks in an Artist/Album/Title layout, scans them with the fake
analyzer (deterministic, no models), and exports the library with ``export_static``.
"""

from __future__ import annotations

import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

from moody.analysis.analyzer import FakeAnalyzer
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
        for i in range(N_TRACKS):
            write_wav(root / f"Artist {i % 6}" / f"Album {i % 9}" / f"Track {i:02d}.wav", 110 + 17 * i)
        engine = init_db(f"sqlite:///{Path(tmp) / 'moody.db'}")
        try:
            sessions = session_factory(engine)
            run_scan(root, sessions, FakeAnalyzer)
            report = export_static(sessions, out)
        finally:
            engine.dispose()
    print(f"e2e fixture: {report.tracks} tracks, {report.files} files in {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())

"""Deterministic synthetic audio for tests (no binary fixtures in the repo)."""

from pathlib import Path

import numpy as np
import soundfile as sf

FORMATS = {
    ".wav": ("WAV", "PCM_16"),
    ".flac": ("FLAC", "PCM_16"),
    ".ogg": ("OGG", "VORBIS"),
    ".mp3": ("MP3", "MPEG_LAYER_III"),
}


def write_tone(
    path: Path, freq: float = 440.0, seconds: float = 1.0, sr: int = 44100, **tags: str
) -> Path:
    t = np.arange(int(seconds * sr)) / sr
    y = (0.2 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    fmt, subtype = FORMATS[path.suffix]
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, y, sr, format=fmt, subtype=subtype)
    if tags:
        import mutagen

        audio = mutagen.File(path, easy=True)
        if audio.tags is None:
            audio.add_tags()
        for key, value in tags.items():
            audio[key] = value
        audio.save()
    return path

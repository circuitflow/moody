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


def write_clip(path: Path, kind: str, seconds: float = 20.0, sr: int = 44100) -> Path:
    """Deterministic musical-ish clips with known character.

    - ``calm``: soft sustained C-major triad, no pulse
    - ``pulse``: loud A-minor triad with a percussive click track at 120 BPM
    - ``noise``: loud distorted noise bursts at 160 BPM
    """
    rng = np.random.default_rng(0)
    t = np.arange(int(seconds * sr)) / sr

    def triad(freqs: tuple[float, ...]) -> np.ndarray:
        return sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)

    def clicks(bpm: float) -> np.ndarray:
        env = np.zeros_like(t)
        period = int(sr * 60 / bpm)
        decay = np.exp(-np.arange(int(0.05 * sr)) / (0.01 * sr))
        for start in range(0, len(t) - len(decay), period):
            env[start : start + len(decay)] += decay
        return env

    if kind == "calm":
        y = 0.08 * triad((261.63, 329.63, 392.0))
    elif kind == "pulse":
        y = 0.3 * triad((220.0, 261.63, 329.63)) + 0.6 * clicks(120) * rng.standard_normal(len(t))
    elif kind == "noise":
        y = np.tanh(
            3 * clicks(160) * rng.standard_normal(len(t)) + 0.3 * rng.standard_normal(len(t))
        )
    else:
        raise ValueError(kind)
    peak = {"calm": 0.1, "pulse": 0.9, "noise": 0.95}[kind]
    y = (peak * y / np.max(np.abs(y))).astype(np.float32)
    fmt, subtype = FORMATS[path.suffix]
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, y, sr, format=fmt, subtype=subtype)
    return path

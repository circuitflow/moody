"""The real analyzer: Essentia DSP plus pretrained TensorFlow models.

Requires the ``analysis`` extra (essentia-tensorflow) and downloaded models
(``moody models pull``). essentia is imported lazily so the base install works without it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from moody.analysis import va
from moody.analysis.analyzer import AnalysisError, TrackAnalysis
from moody.analysis.features2007 import RawMeasurements, thesis_features
from moody.analysis.models import (
    EFFNET,
    MODELS,
    MOOD_CLASSIFIERS,
    MUSICNN,
    ModelMeta,
    model_path,
    read_meta,
    status,
)

EMBEDDING_SR = 16000
DSP_SR = 44100
MIN_SECONDS = 3.0
# TensorflowPredictMusiCNN: 93-frame patch hop, 256-sample frame hop at 16 kHz.
MUSICNN_HOP_S = 93 * 256 / EMBEDDING_SR
VA_HEAD = "deam-msd-musicnn-2"
MOODTHEME_HEAD = "mtg_jamendo_moodtheme-discogs-effnet-1"


def _f32(x: Any) -> npt.NDArray[np.float32]:
    return np.asarray(x, dtype=np.float32)


def _essentia() -> Any:
    import essentia
    import essentia.standard as es

    essentia.log.infoActive = False
    essentia.log.warningActive = False
    return es


class EssentiaAnalyzer:
    def __init__(self, models_dir: Path) -> None:
        missing = [name for name, ok in status(models_dir).items() if not ok]
        if missing:
            raise FileNotFoundError(
                f"missing models in {models_dir}: {', '.join(missing)}; run `moody models pull`"
            )
        es = _essentia()
        self._es = es
        self.meta: dict[str, ModelMeta] = {m.name: read_meta(models_dir, m.name) for m in MODELS}

        def graph(name: str) -> str:
            return str(model_path(models_dir, name))

        self.effnet = es.TensorflowPredictEffnetDiscogs(
            graphFilename=graph(EFFNET), output=self.meta[EFFNET].output
        )
        self.musicnn = es.TensorflowPredictMusiCNN(
            graphFilename=graph(MUSICNN), output=self.meta[MUSICNN].output
        )
        self.heads: dict[str, Any] = {}
        for spec in MODELS:
            if spec.role != "head":
                continue
            meta = self.meta[spec.name]
            kwargs: dict[str, str] = {"graphFilename": graph(spec.name), "output": meta.output}
            if meta.input:
                kwargs["input"] = meta.input
            self.heads[spec.name] = es.TensorflowPredict2D(**kwargs)

    def _head(self, name: str, embeddings: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
        return _f32(self.heads[name](embeddings))

    def analyze(self, path: Path) -> TrackAnalysis:
        es = self._es
        try:
            audio16 = _f32(
                es.MonoLoader(filename=str(path), sampleRate=EMBEDDING_SR, resampleQuality=4)()
            )
        except RuntimeError as exc:
            raise AnalysisError(f"cannot decode {path.name}: {exc}") from exc
        if len(audio16) < MIN_SECONDS * EMBEDDING_SR:
            raise AnalysisError(f"{path.name} is shorter than {MIN_SECONDS:.0f} s")

        musicnn_emb = _f32(self.musicnn(audio16))
        effnet_emb = _f32(self.effnet(audio16))

        # Valence/arousal per MusiCNN patch -> [-1, 1], smoothed into a trajectory.
        classes = self.meta[VA_HEAD].classes
        raw = self._head(VA_HEAD, musicnn_emb)
        va_raw = raw[:, [classes.index("valence"), classes.index("arousal")]]
        per_patch = va.normalize(va_raw)
        trajectory = va.smooth(per_patch, k=3)
        valence, arousal = (float(x) for x in per_patch.mean(axis=0))

        mood_probs: dict[str, float] = {}
        for mood in MOOD_CLASSIFIERS:
            name = f"mood_{mood}-discogs-effnet-1"
            probs = self._head(name, effnet_emb).mean(axis=0)
            mood_probs[mood] = float(probs[self.meta[name].classes.index(mood)])

        tag_means = self._head(MOODTHEME_HEAD, effnet_emb).mean(axis=0)
        tag_probs = {
            tag: float(p)
            for tag, p in zip(self.meta[MOODTHEME_HEAD].classes, tag_means, strict=True)
        }

        measurements, key, scale = dsp_measurements(path)
        return TrackAnalysis(
            valence=valence,
            arousal=arousal,
            segments=tuple(
                (i * MUSICNN_HOP_S, float(v), float(a)) for i, (v, a) in enumerate(trajectory)
            ),
            mood_probs=mood_probs,
            tag_probs=tag_probs,
            bpm=measurements.bpm,
            key=key,
            scale=scale,
            loudness_lufs=measurements.loudness_lufs,
            features_2007=thesis_features(measurements),
            embeddings={
                EFFNET: effnet_emb.mean(axis=0),
                MUSICNN: musicnn_emb.mean(axis=0),
            },
        )


def dsp_measurements(path: Path) -> tuple[RawMeasurements, str, str]:
    """Tempo, key, loudness and chords (Essentia DSP only; no models needed)."""
    es = _essentia()
    stereo, sr, *_ = es.AudioLoader(filename=str(path))()
    loudness = float(es.LoudnessEBUR128(sampleRate=sr)(stereo)[2])
    mono = _f32(es.MonoLoader(filename=str(path), sampleRate=DSP_SR)())

    bpm, _ticks, confidence, _estimates, intervals = es.RhythmExtractor2013(method="multifeature")(
        mono
    )
    key, scale, _strength = es.KeyExtractor(sampleRate=DSP_SR)(mono)
    chords, strengths = _chords(mono)
    return (
        RawMeasurements(
            chord_labels=tuple(str(c) for c in chords),
            chord_strengths=tuple(float(s) for s in strengths),
            bpm=float(bpm),
            bpm_confidence=float(confidence),
            beat_intervals=tuple(float(x) for x in intervals),
            loudness_lufs=loudness,
        ),
        str(key),
        str(scale),
    )


def _chords(mono: npt.NDArray[np.float32]) -> tuple[list[str], list[float]]:
    es = _essentia()
    frame_size, hop = 4096, 2048
    window = es.Windowing(type="blackmanharris62")
    spectrum = es.Spectrum()
    peaks = es.SpectralPeaks(
        orderBy="magnitude",
        magnitudeThreshold=1e-5,
        minFrequency=20,
        maxFrequency=3500,
        maxPeaks=60,
        sampleRate=DSP_SR,
    )
    hpcp = es.HPCP(sampleRate=DSP_SR)
    frames = [
        hpcp(*peaks(spectrum(window(frame))))
        for frame in es.FrameGenerator(mono, frameSize=frame_size, hopSize=hop, startFromZero=True)
    ]
    if not frames:
        return [], []
    chords, strengths = es.ChordsDetection(hopSize=hop, sampleRate=DSP_SR)(_f32(frames))
    return list(chords), list(strengths)

"""Which output column of Essentia's valence/arousal heads tracks which human rating?

Runs the MSD-MusiCNN embedding model and the DEAM and emoMusic heads on a sample of DEAM
clips and compares the outputs with DEAM's song-level (static) annotations. Writes a JSON
report. Run from ``backend/`` with the ``analysis`` extra and pulled models:

    uv run python ../eval/deam_orientation.py DEAM_DIR MODELS_DIR OUT_JSON [--n 400]

Note: the DEAM head was trained on DEAM, so its scores here are optimistic. The point of this
script is the *orientation* of the columns (``contrast_r``), which training-set overlap does
not change. The emoMusic head was trained on a different dataset, so it acts as a
cross-dataset check.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import random
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from moody.analysis.models import MUSICNN, model_path, pipeline_version, read_meta
from moody.evaluation import orientation_report

HEADS = ("deam-msd-musicnn-2", "emomusic-msd-musicnn-2")


def load_annotations(deam_dir: Path) -> dict[int, tuple[float, float]]:
    """song_id -> (valence_mean, arousal_mean) on the 1-9 scale, for the 45 s clips (ids <= 2000).

    Looks for DEAM's song-level ("static", "averaged") annotation CSVs rather than one exact
    file name, and strips the stray spaces DEAM has in its column headers.
    """
    out: dict[int, tuple[float, float]] = {}
    csvs = sorted(deam_dir.rglob("*.csv"))
    for path in csvs:
        name = path.name.lower()
        if "static" not in name or "averag" not in name:
            continue
        with path.open(newline="") as f:
            reader = csv.DictReader(f)
            reader.fieldnames = [field.strip() for field in reader.fieldnames or []]
            if not {"song_id", "valence_mean", "arousal_mean"} <= set(reader.fieldnames):
                continue
            for row in reader:
                song_id = int(float(row["song_id"]))
                if song_id <= 2000:
                    out[song_id] = (float(row["valence_mean"]), float(row["arousal_mean"]))
    if not out:
        found = [str(p.relative_to(deam_dir)) for p in csvs]
        raise FileNotFoundError(f"no static song-level annotations found; csv files: {found}")
    return out


def markdown_summary(report: dict[str, Any]) -> str:
    """A readable table of ``report["heads"]`` (as written by ``main``)."""
    rows = [
        "| model | n | contrast_r | verdict | r(col0, V) | r(col0, A) | r(col1, V) | r(col1, A)"
        " | r(col0, col1) | r(V, A) human |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, h in report["heads"].items():
        r = h["pearson"]
        rows.append(
            f"| {name} | {h['n']} | {h['contrast_r']:+.2f} | {h['verdict']} "
            f"| {r['col0_vs_valence']:+.2f} | {r['col0_vs_arousal']:+.2f} "
            f"| {r['col1_vs_valence']:+.2f} | {r['col1_vs_arousal']:+.2f} "
            f"| {h['outputs_corr']:+.2f} | {h['annotations_corr']:+.2f} |"
        )
    return (
        f"# DEAM orientation check\n\n{report['dataset']}; sample of {report['sample']['n']} "
        f"(seed {report['sample']['seed']}); pipeline {report['pipeline_version']}.\n\n"
        "col0/col1 are the model's outputs in metadata order (`valence`, `arousal`). "
        "`contrast_r` = corr(col0 - col1, valence - arousal): positive means the columns are "
        "labelled correctly, negative means they are swapped.\n\n" + "\n".join(rows) + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("deam_dir", type=Path)
    parser.add_argument("models_dir", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--n", type=int, default=400)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    import essentia
    import essentia.standard as es

    essentia.log.infoActive = False
    essentia.log.warningActive = False

    annotations = load_annotations(args.deam_dir)
    audio = {int(p.stem): p for p in args.deam_dir.rglob("*.mp3") if p.stem.isdigit()}
    ids = sorted(set(annotations) & set(audio))
    random.Random(args.seed).shuffle(ids)
    ids = ids[: args.n]
    print(f"{len(annotations)} annotated clips, {len(audio)} audio files, using {len(ids)}")

    embed = es.TensorflowPredictMusiCNN(
        graphFilename=str(model_path(args.models_dir, MUSICNN)),
        output=read_meta(args.models_dir, MUSICNN).output,
    )
    heads = {}
    for name in HEADS:
        meta = read_meta(args.models_dir, name)
        assert meta.classes == ("valence", "arousal"), meta.classes
        heads[name] = es.TensorflowPredict2D(
            graphFilename=str(model_path(args.models_dir, name)),
            output=meta.output,
            **({"input": meta.input} if meta.input else {}),
        )

    preds: dict[str, list[list[float]]] = {name: [] for name in HEADS}
    used: list[int] = []
    started = time.monotonic()
    for i, song_id in enumerate(ids, 1):
        try:
            wave = es.MonoLoader(
                filename=str(audio[song_id]), sampleRate=16000, resampleQuality=4
            )()
            emb = embed(wave)
        except RuntimeError as exc:
            print(f"skip {song_id}: {exc}", file=sys.stderr)
            continue
        for name, head in heads.items():
            preds[name].append(np.asarray(head(emb)).mean(axis=0).tolist())
        used.append(song_id)
        if i % 50 == 0:
            print(f"{i}/{len(ids)} clips ({time.monotonic() - started:.0f} s)")

    v = np.array([annotations[s][0] for s in used])
    a = np.array([annotations[s][1] for s in used])
    report: dict[str, Any] = {
        "dataset": "DEAM static song-level annotations (1-9), 45 s clips",
        "sample": {"n": len(used), "seed": args.seed},
        "pipeline_version": pipeline_version(),
        "essentia": essentia.__version__,
        "platform": platform.platform(),
        "seconds": round(time.monotonic() - started),
        "heads": {name: orientation_report(np.array(preds[name]), v, a) for name in HEADS},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    summary = markdown_summary(report)
    args.out.with_suffix(".md").write_text(summary)
    print(json.dumps(report["heads"], indent=2))
    print(summary)


if __name__ == "__main__":
    main()

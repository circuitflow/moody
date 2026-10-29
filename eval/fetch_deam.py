"""Download and unpack the DEAM dataset (audio + annotations) for evaluation.

DEAM: MediaEval Database for Emotional Analysis in Music, https://cvml.unige.ch/databases/DEAM/
It is free for non-commercial research use; Moody only downloads it in CI (or locally) and never
redistributes it.

Sources, in order:
1. Kaggle mirror (audio + annotations), if KAGGLE_USERNAME and KAGGLE_KEY are set
2. the original site (unreachable from GitHub runners as of 2026-10)
3. annotations only: the Zenodo record, used when a source above lacked them

Usage: python eval/fetch_deam.py DEST_DIR
"""

from __future__ import annotations

import os
import subprocess
import sys
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

KAGGLE_DATASET = "imsparsh/deam-mediaeval-dataset-emotional-analysis-in-music"
ORIGINAL = [
    "https://cvml.unige.ch/databases/DEAM/DEAM_Annotations.zip",
    "https://cvml.unige.ch/databases/DEAM/DEAM_audio.zip",
]
ZENODO_ANNOTATIONS = "https://zenodo.org/api/records/11400122/files/DEAM_Annotations.zip/content"
MIN_CLIPS = 1000  # DEAM has 1802 audio files; fewer means a partial download


def mp3_count(dest: Path) -> int:
    return sum(1 for _ in dest.rglob("*.mp3"))


def has_annotations(dest: Path) -> bool:
    return any(
        "static" in p.name.lower() and "averag" in p.name.lower() for p in dest.rglob("*.csv")
    )


def unzip_all(dest: Path) -> None:
    """Unpack every zip under dest (DEAM nests archives) and delete it afterwards."""
    while zips := list(dest.rglob("*.zip")):
        for archive in zips:
            print("unpacking", archive.relative_to(dest), flush=True)
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(archive.parent)
            archive.unlink()


def download(url: str, dest: Path, name: str) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / name
    print("downloading:", url, flush=True)
    tmp = target.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=30) as resp, tmp.open("wb") as out:
        while chunk := resp.read(1 << 20):
            out.write(chunk)
    tmp.replace(target)


def from_kaggle(dest: Path) -> None:
    if not (os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY")):
        raise RuntimeError("KAGGLE_USERNAME / KAGGLE_KEY not set")
    cmd = ["uvx", "kaggle", "datasets", "download", "-d", KAGGLE_DATASET, "-p", str(dest)]
    subprocess.run(cmd, check=True)


def from_original_site(dest: Path) -> None:
    for url in ORIGINAL:
        download(url, dest, url.rsplit("/", 1)[-1])


def main(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if (dest / ".complete").exists():
        print("DEAM already unpacked in", dest)
        return

    sources: list[tuple[str, Callable[[Path], None]]] = [
        ("kaggle", from_kaggle),
        ("original site", from_original_site),
    ]
    for name, fetch in sources:
        try:
            fetch(dest)
            unzip_all(dest)
        except Exception as exc:
            print(f"source '{name}' failed: {type(exc).__name__}: {exc}", flush=True)
            continue
        if mp3_count(dest) >= MIN_CLIPS:
            print(f"audio from {name}")
            break
    if mp3_count(dest) < MIN_CLIPS:
        sys.exit(
            f"no DEAM audio: found {mp3_count(dest)} mp3 files. Add KAGGLE_USERNAME and "
            "KAGGLE_KEY repository secrets (kaggle.com > Settings > API > Create New Token)."
        )

    if not has_annotations(dest):
        print("annotations missing from the audio source; using Zenodo")
        download(ZENODO_ANNOTATIONS, dest, "DEAM_Annotations.zip")
        unzip_all(dest)
    if not has_annotations(dest):
        sys.exit("no DEAM static annotations found after all sources")

    (dest / ".complete").touch()
    print(f"ready: {mp3_count(dest)} mp3 files, annotations present")


if __name__ == "__main__":
    main(Path(sys.argv[1]))

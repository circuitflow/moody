"""Download and unpack the DEAM dataset (audio + annotations) for evaluation.

DEAM: MediaEval Database for Emotional Analysis in Music, https://cvml.unige.ch/databases/DEAM/
It is free for non-commercial research use; Moody only downloads it in CI and never
redistributes it. Tries the Zenodo mirror first, then the original site.

Usage: python eval/fetch_deam.py DEST_DIR
"""

from __future__ import annotations

import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ZENODO_RECORD = "https://zenodo.org/api/records/11400122"
ORIGINAL = [
    "https://cvml.unige.ch/databases/DEAM/DEAM_Annotations.zip",
    "https://cvml.unige.ch/databases/DEAM/DEAM_audio.zip",
]


def zenodo_urls() -> list[str]:
    with urllib.request.urlopen(ZENODO_RECORD, timeout=60) as resp:
        record = json.load(resp)
    files = record.get("files", [])
    print("zenodo files:", [(f["key"], f["size"]) for f in files])
    wanted = [
        f
        for f in files
        if f["key"].lower().endswith(".zip")
        and any(word in f["key"].lower() for word in ("audio", "annotation"))
    ]
    return [f["links"]["self"] for f in wanted]


def download(url: str, dest: Path) -> Path:
    name = url.rstrip("/").split("/")[-1]
    if name == "content":  # Zenodo links end in /files/<name>/content
        name = url.rstrip("/").split("/")[-2]
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / name
    if target.exists():
        print("cached:", target)
        return target
    print("downloading:", url)
    tmp = target.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=600) as resp, tmp.open("wb") as out:
        while chunk := resp.read(1 << 20):
            out.write(chunk)
    tmp.replace(target)
    return target


def main(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if (dest / ".complete").exists():
        print("DEAM already unpacked in", dest)
        return
    try:
        urls = zenodo_urls()
        if len(urls) < 2:
            raise RuntimeError(f"expected audio + annotation archives on Zenodo, got {urls}")
    except Exception as exc:
        print("zenodo unavailable, using the original site:", exc)
        urls = ORIGINAL
    for url in urls:
        archive = download(url, dest / "_zips")
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)
        archive.unlink()  # keep only the unpacked files (smaller CI cache)
    (dest / ".complete").touch()
    csvs = sorted(str(p.relative_to(dest)) for p in dest.rglob("*.csv"))
    mp3s = sum(1 for _ in dest.rglob("*.mp3"))
    print(f"unpacked {mp3s} mp3 files and {len(csvs)} csv files")


if __name__ == "__main__":
    main(Path(sys.argv[1]))

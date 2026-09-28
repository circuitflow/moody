"""Registry of the pretrained Essentia models Moody uses, with checksum-pinned downloads.

Output node names and class labels are read from each model's JSON metadata (as the Essentia
docs recommend) rather than hard-coded.
"""

from __future__ import annotations

import hashlib
import json
import logging
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Literal

log = logging.getLogger(__name__)

BASE_URL = "https://essentia.upf.edu/models"
LOCK_FILE = "models.lock.json"
# Bump when analysis code changes in a way that should trigger re-analysis.
PIPELINE_REV = 1

EFFNET = "discogs-effnet-bs64-1"
MUSICNN = "msd-musicnn-1"


@dataclass(frozen=True)
class ModelSpec:
    name: str
    subdir: str
    role: Literal["embedding", "head"]
    embedding: str | None = None  # for heads: which extractor feeds it

    @property
    def urls(self) -> dict[str, str]:
        return {ext: f"{BASE_URL}/{self.subdir}/{self.name}.{ext}" for ext in ("pb", "json")}


MOOD_CLASSIFIERS = ("happy", "sad", "aggressive", "relaxed", "party")

MODELS: tuple[ModelSpec, ...] = (
    ModelSpec(EFFNET, "feature-extractors/discogs-effnet", "embedding"),
    ModelSpec(MUSICNN, "feature-extractors/musicnn", "embedding"),
    ModelSpec("deam-msd-musicnn-2", "classification-heads/deam", "head", MUSICNN),
    ModelSpec("emomusic-msd-musicnn-2", "classification-heads/emomusic", "head", MUSICNN),
    *(
        ModelSpec(f"mood_{m}-discogs-effnet-1", f"classification-heads/mood_{m}", "head", EFFNET)
        for m in MOOD_CLASSIFIERS
    ),
    ModelSpec(
        "mtg_jamendo_moodtheme-discogs-effnet-1",
        "classification-heads/mtg_jamendo_moodtheme",
        "head",
        EFFNET,
    ),
)
BY_NAME = {spec.name: spec for spec in MODELS}

Fetcher = Callable[[str], Iterable[bytes]]


class ChecksumError(RuntimeError):
    pass


def http_fetch(url: str) -> Iterator[bytes]:
    with urllib.request.urlopen(url, timeout=60) as resp:
        while chunk := resp.read(1 << 16):
            yield chunk


def load_lock(path: Path | None = None) -> dict[str, dict[str, str | None]]:
    text = (
        path.read_text() if path else resources.files(__package__).joinpath(LOCK_FILE).read_text()
    )
    data: dict[str, dict[str, str | None]] = json.loads(text)["models"]
    return data


def save_lock(lock: dict[str, dict[str, str | None]], path: Path) -> None:
    path.write_text(json.dumps({"version": 1, "models": lock}, indent=2, sort_keys=True) + "\n")


def default_lock_path() -> Path:
    return Path(str(resources.files(__package__).joinpath(LOCK_FILE)))


def pipeline_version() -> str:
    """Short hash of the pinned models plus PIPELINE_REV; stored with every analysis."""
    lock = json.dumps(load_lock(), sort_keys=True)
    return hashlib.blake2b(f"{lock}|{PIPELINE_REV}".encode(), digest_size=6).hexdigest()


def model_path(models_dir: Path, name: str, ext: str = "pb") -> Path:
    return models_dir / f"{name}.{ext}"


def _download(url: str, dest: Path, expected: str | None, fetch: Fetcher) -> str:
    tmp = dest.with_suffix(dest.suffix + ".part")
    h = hashlib.sha256()
    try:
        with tmp.open("wb") as f:
            for chunk in fetch(url):
                h.update(chunk)
                f.write(chunk)
        digest = h.hexdigest()
        if expected and digest != expected:
            raise ChecksumError(f"{url}: expected sha256 {expected}, got {digest}")
        tmp.replace(dest)
        return digest
    finally:
        tmp.unlink(missing_ok=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def pull(
    models_dir: Path,
    *,
    update_lock: bool = False,
    lock_path: Path | None = None,
    fetch: Fetcher = http_fetch,
) -> dict[str, dict[str, str | None]]:
    """Download every model (.pb + .json) into ``models_dir``, verifying pinned checksums.

    Files already present with the right checksum are skipped. With ``update_lock``, missing or
    changed checksums are recorded in the lock file instead of raising.
    """
    lock_path = lock_path or default_lock_path()
    lock = load_lock(lock_path)
    models_dir.mkdir(parents=True, exist_ok=True)
    for spec in MODELS:
        entry = lock.setdefault(spec.name, {"pb": None, "json": None})
        for ext, url in spec.urls.items():
            dest = model_path(models_dir, spec.name, ext)
            expected = None if update_lock else entry.get(ext)
            if dest.exists() and expected and sha256_file(dest) == expected:
                continue
            if not expected and not update_lock:
                log.warning("%s.%s has no pinned checksum; run with --update-lock", spec.name, ext)
            log.info("downloading %s", url)
            entry[ext] = _download(url, dest, expected, fetch)
    if update_lock:
        save_lock(lock, lock_path)
    return lock


def status(models_dir: Path) -> dict[str, bool]:
    return {
        spec.name: all(model_path(models_dir, spec.name, ext).exists() for ext in ("pb", "json"))
        for spec in MODELS
    }


@dataclass(frozen=True)
class ModelMeta:
    """What the analyzer needs from a model's JSON metadata."""

    name: str
    input: str | None
    output: str
    classes: tuple[str, ...]


def read_meta(models_dir: Path, name: str) -> ModelMeta:
    meta: dict[str, Any] = json.loads(model_path(models_dir, name, "json").read_text())
    schema = meta.get("schema", {})
    outputs: list[dict[str, Any]] = schema.get("outputs", [])
    role = BY_NAME[name].role
    purpose = "embeddings" if role == "embedding" else "predictions"
    chosen = next((o for o in outputs if o.get("output_purpose") == purpose), None)
    if chosen is None:
        raise ValueError(f"{name}: no output with purpose {purpose!r} in metadata")
    inputs: list[dict[str, Any]] = schema.get("inputs", [])
    return ModelMeta(
        name=name,
        input=inputs[0]["name"] if inputs else None,
        output=chosen["name"],
        classes=tuple(meta.get("classes", [])),
    )

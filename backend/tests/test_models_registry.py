import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from moody.analysis import models


def fake_fetch(url: str) -> Iterator[bytes]:
    yield f"payload for {url}".encode()


def sha(url: str) -> str:
    return hashlib.sha256(f"payload for {url}".encode()).hexdigest()


@pytest.fixture
def lock_path(tmp_path: Path) -> Path:
    path = tmp_path / "models.lock.json"
    path.write_text(models.default_lock_path().read_text())
    return path


def test_registry_covers_all_models_in_lock() -> None:
    assert set(models.load_lock()) == set(models.BY_NAME)
    heads = [m for m in models.MODELS if m.role == "head"]
    assert all(h.embedding in models.BY_NAME for h in heads)


def test_update_lock_records_checksums(tmp_path: Path, lock_path: Path) -> None:
    models.pull(tmp_path / "m", update_lock=True, lock_path=lock_path, fetch=fake_fetch)
    lock = models.load_lock(lock_path)
    spec = models.BY_NAME["deam-msd-musicnn-2"]
    assert lock[spec.name]["pb"] == sha(spec.urls["pb"])
    assert all(models.status(tmp_path / "m").values())


def test_pull_verifies_and_skips_present_files(tmp_path: Path, lock_path: Path) -> None:
    models.pull(tmp_path / "m", update_lock=True, lock_path=lock_path, fetch=fake_fetch)
    calls: list[str] = []

    def counting_fetch(url: str) -> Iterator[bytes]:
        calls.append(url)
        return fake_fetch(url)

    models.pull(tmp_path / "m", lock_path=lock_path, fetch=counting_fetch)
    assert calls == []


def test_checksum_mismatch_raises_and_leaves_no_file(tmp_path: Path, lock_path: Path) -> None:
    data = json.loads(lock_path.read_text())
    data["models"]["msd-musicnn-1"]["pb"] = "0" * 64
    lock_path.write_text(json.dumps(data))
    with pytest.raises(models.ChecksumError):
        models.pull(tmp_path / "m", lock_path=lock_path, fetch=fake_fetch)
    assert not models.model_path(tmp_path / "m", "msd-musicnn-1").exists()
    assert not list((tmp_path / "m").glob("*.part"))


def test_read_meta_picks_output_by_purpose(tmp_path: Path) -> None:
    meta = {
        "classes": ["valence", "arousal"],
        "schema": {
            "inputs": [{"name": "model/Placeholder"}],
            "outputs": [
                {"name": "model/Identity", "output_purpose": "predictions"},
                {"name": "model/dense/BiasAdd", "output_purpose": ""},
            ],
        },
    }
    (tmp_path / "deam-msd-musicnn-2.json").write_text(json.dumps(meta))
    parsed = models.read_meta(tmp_path, "deam-msd-musicnn-2")
    assert (parsed.input, parsed.output, parsed.classes) == (
        "model/Placeholder",
        "model/Identity",
        ("valence", "arousal"),
    )


def test_pipeline_version_is_stable_short_hash() -> None:
    assert models.pipeline_version() == models.pipeline_version()
    assert len(models.pipeline_version()) == 12

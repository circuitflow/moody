"""Content fingerprint that survives renames and moves without reading whole files."""

import hashlib
from pathlib import Path

CHUNK = 1 << 20  # 1 MiB


def content_hash(path: Path) -> str:
    """BLAKE2b-128 over the file size plus its first and last MiB (hex, 32 chars)."""
    size = path.stat().st_size
    h = hashlib.blake2b(digest_size=16)
    h.update(size.to_bytes(8, "little"))
    with path.open("rb") as f:
        h.update(f.read(CHUNK))
        if size > 2 * CHUNK:
            f.seek(-CHUNK, 2)
            h.update(f.read(CHUNK))
        elif size > CHUNK:
            h.update(f.read())
    return h.hexdigest()

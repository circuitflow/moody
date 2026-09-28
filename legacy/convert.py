"""Convert the 2007 thesis training set into a portable CSV.

Usage (one-off; needs numpy to unpickle the 2007 numpy arrays):

    git clone https://github.com/circuitflow/moody-2007 /tmp/moody-2007
    uv run --no-project --with numpy python legacy/convert.py /tmp/moody-2007

Joins ``training.dat`` (octant class + 5 features), ``training_info.dat`` (title, octant,
Hevner adjective, AllMusic mood) and the pickled playlist
``playlists/372Songs_3MoodValues_Lyrics.mpl`` (ID3 artist/album/genre, lyric-affect scores).
Local file paths and lyric text are deliberately dropped.
"""

from __future__ import annotations

import csv
import pickle
import sys
from pathlib import Path

OCTANTS = [
    "Pleasure", "Excitement", "Arousal", "Distress",
    "Displeasure", "Depression", "Sleepiness", "Relaxation",
]
FEATURES = ["mode", "harmony", "tempo", "rhythm", "loudness"]
OUT = Path(__file__).parent / "data" / "thesis2007_training.csv"


def main(src: Path) -> None:
    rows = [line.split() for line in (src / "training.dat").read_text().splitlines()]
    info = [
        line.split("\t")
        for line in (src / "training_info.dat").read_text(encoding="latin1").splitlines()
    ]
    with open(src / "playlists" / "372Songs_3MoodValues_Lyrics.mpl", "rb") as f:
        playlist = pickle.load(f, encoding="latin1")
    by_title = {rec["ID3"]["songTitle"].strip().lower(): rec for _path, rec in playlist}

    out_rows = []
    for row, (title, octant, hevner, amg) in zip(rows, info, strict=True):
        assert OCTANTS[int(row[0])] == octant, (title, row[0], octant)
        rec = by_title.get(title.strip().lower())
        id3 = rec["ID3"] if rec else {}
        lyrics = rec["Features"].get("moodLyrics") if rec else None
        out_rows.append({
            "title": title.strip(),
            "artist": id3.get("songArtist", "").strip(),
            "album": id3.get("songAlbum", "").strip(),
            "genre": id3.get("songGenre", "").strip(),
            "amg_mood": amg.strip(),
            "octant_2007": octant,
            "hevner_2007": hevner.strip().lower(),
            **{name: f"{float(v):.4f}" for name, v in zip(FEATURES, row[1:], strict=True)},
            "lyrics_octant": lyrics[0][0] if lyrics else "",
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(out_rows[0]))
        writer.writeheader()
        writer.writerows(out_rows)
    matched = sum(1 for r in out_rows if r["artist"])
    print(f"wrote {len(out_rows)} rows ({matched} with ID3 metadata) to {OUT}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))

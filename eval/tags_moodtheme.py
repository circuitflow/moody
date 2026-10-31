"""Mood/theme tag accuracy of the Discogs-EffNet MTG-Jamendo head on the demo tracks.

The demo tracks are a CC BY / CC BY-SA, tag-stratified subset of the MTG-Jamendo mood/theme
split-0 test set, so this is a held-out evaluation (the head was trained on the training split),
but on a subset: the report says how many tracks and how common each tag is.

    MOODY_DATA_DIR=<merged demo data> uv run python ../eval/tags_moodtheme.py tracks.csv out.json

Writes per-tag ROC-AUC and average precision (PR-AUC) for tags with at least 5 positives and 5
negatives, plus their macro averages.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from sqlalchemy import select

from moody.config import get_settings
from moody.demo import jamendo_id_of, read_csv
from moody.evaluation import average_precision, roc_auc
from moody.store import init_db, session_factory
from moody.store.models import Analysis, Track

MIN_CLASS = 5


def evaluate(truth: dict[int, set[str]], preds: dict[int, dict[str, float]]) -> dict[str, object]:
    ids = sorted(set(truth) & set(preds))
    tags = sorted({t for i in ids for t in preds[i]})
    per_tag = []
    for tag in tags:
        y = np.array([tag in truth[i] for i in ids])
        if y.sum() < MIN_CLASS or (~y).sum() < MIN_CLASS:
            continue
        s = np.array([preds[i].get(tag, 0.0) for i in ids])
        per_tag.append(
            {
                "tag": tag,
                "positives": int(y.sum()),
                "prevalence": round(float(y.mean()), 4),
                "roc_auc": round(roc_auc(s, y), 4),
                "pr_auc": round(average_precision(s, y), 4),
            }
        )
    return {
        "tracks": len(ids),
        "tags_evaluated": len(per_tag),
        "macro_roc_auc": round(float(np.mean([t["roc_auc"] for t in per_tag])), 4)
        if per_tag
        else None,
        "macro_pr_auc": round(float(np.mean([t["pr_auc"] for t in per_tag])), 4)
        if per_tag
        else None,
        "per_tag": sorted(per_tag, key=lambda t: -float(t["roc_auc"])),  # type: ignore[arg-type]
        "note": (
            "Held-out MTG-Jamendo mood/theme split-0 test tracks, restricted to CC BY / CC BY-SA "
            "and stratified by tag. ROC-AUC is independent of how common a tag is; PR-AUC is not "
            "(compare it with the prevalence)."
        ),
    }


def main(tracks_csv: Path, out: Path) -> None:
    truth = {t.jamendo_id: set(t.tags) for t in read_csv(tracks_csv)}
    engine = init_db(get_settings().database_url)
    preds: dict[int, dict[str, float]] = {}
    with session_factory(engine)() as session:
        for path, probs in session.execute(
            select(Track.path, Analysis.tag_probs).join(Analysis, Analysis.track_id == Track.id)
        ):
            jid = jamendo_id_of(path)
            if jid is not None:
                preds[jid] = probs
    engine.dispose()
    report = evaluate(truth, preds)
    out.write_text(json.dumps(report, indent=2))
    print(
        f"{report['tracks']} tracks, {report['tags_evaluated']} tags: "
        f"macro ROC-AUC {report['macro_roc_auc']}, macro PR-AUC {report['macro_pr_auc']}"
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))

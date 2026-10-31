"""Render the evaluation results for the README and the app's About page.

    uv run python ../eval/render.py      (from backend/)

Reads ``eval/results/deam_orientation.json`` and, when present, ``tags_moodtheme.json``
(pushed by the Demo bundle workflow), and writes:

- ``frontend/src/features/about/evaluation.json``: the numbers the About page shows;
- the section between ``<!-- eval:start -->`` and ``<!-- eval:end -->`` in ``README.md``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "eval" / "results"
ABOUT = ROOT / "frontend" / "src" / "features" / "about" / "evaluation.json"
README = ROOT / "README.md"
START, END = "<!-- eval:start -->", "<!-- eval:end -->"


def _load(name: str) -> dict[str, Any] | None:
    path = RESULTS / name
    return json.loads(path.read_text()) if path.exists() else None


def summarize() -> dict[str, Any]:
    out: dict[str, Any] = {"deam": None, "tags": None}
    deam = _load("deam_orientation.json")
    if deam:
        prod = deam["production"]
        loud = deam["confounds"].get("loudness", {})
        out["deam"] = {
            "n": prod["n"],
            "valence_r": round(prod["pearson"]["col0_vs_valence"], 2),
            "arousal_r": round(prod["pearson"]["col1_vs_arousal"], 2),
            "contrast_r": round(prod["contrast_r"], 2),
            "predicted_va_corr": round(prod["outputs_corr"], 2),
            "rated_va_corr": round(prod["annotations_corr"], 2),
            "loudness_vs_v_minus_a": {
                "model": round(loud["model_v_minus_a"], 2) if loud else None,
                "listeners": round(loud["human_v_minus_a"], 2) if loud else None,
            },
            "octants": deam.get("octants"),
        }
    tags = _load("tags_moodtheme.json")
    if tags and tags.get("per_tag"):
        per_tag = tags["per_tag"]
        out["tags"] = {
            "tracks": tags["tracks"],
            "tags_evaluated": tags["tags_evaluated"],
            "macro_roc_auc": tags["macro_roc_auc"],
            "macro_pr_auc": tags["macro_pr_auc"],
            "best": per_tag[:5],
            "worst": per_tag[-5:][::-1],
        }
    return out


def _pct(x: float) -> str:
    return f"{x:.0%}"


def markdown(s: dict[str, Any]) -> str:
    lines = ["### How well it works", ""]
    d = s["deam"]
    if d:
        lines += [
            f"**Valence/arousal on DEAM** ({d['n']} clips, ratings by listeners; the head was "
            "trained on DEAM, so these are in-domain and optimistic):",
            "",
            "| | Pearson r |",
            "|---|---|",
            f"| valence | {d['valence_r']:.2f} |",
            f"| arousal | {d['arousal_r']:.2f} |",
            f"| valence minus arousal (do the outputs mean different things?) "
            f"| {d['contrast_r']:.2f} |",
            "",
            f"Predicted valence and arousal correlate at {d['predicted_va_corr']:+.2f}, against "
            f"{d['rated_va_corr']:+.2f} between listeners' ratings: the model leans on one "
            '"intensity" axis. Loudness correlates '
            f"{d['loudness_vs_v_minus_a']['model']:+.2f} with predicted valence minus arousal, "
            f"{d['loudness_vs_v_minus_a']['listeners']:+.2f} with rated: loud music looks happier "
            "to the model than to people.",
            "",
        ]
        o = d.get("octants")
        if o:
            c = o["clear"]
            lines += [
                f"**2007 thesis vs 2026** on Russell's eight octants, DEAM clips whose rated mood "
                f"is clearly away from neutral ({c['2026_head']['n']} clips):",
                "",
                "| model | exact octant | within one octant | mean angle error |",
                "|---|---|---|---|",
            ]
            for key, name in (
                ("2026_head", "2026 (DEAM head)"),
                ("2007_tree", "2007 (decision tree)"),
            ):
                m = c[key]
                if m.get("n"):
                    lines.append(
                        f"| {name} | {_pct(m['exact'])} | {_pct(m['within_one'])} "
                        f"| {m['mean_angle_error_deg']:.0f}° |"
                    )
            lines += ["", f"Always guessing the most common octant: {_pct(c['chance_exact'])}.", ""]
    t = s["tags"]
    if t:
        lines += [
            f"**Mood/theme tags** on {t['tracks']} held-out MTG-Jamendo test tracks "
            f"({t['tags_evaluated']} tags): macro ROC-AUC {t['macro_roc_auc']:.2f}, "
            f"macro PR-AUC {t['macro_pr_auc']:.2f}. Best: "
            + ", ".join(f"{x['tag']} {x['roc_auc']:.2f}" for x in t["best"])
            + "; hardest: "
            + ", ".join(f"{x['tag']} {x['roc_auc']:.2f}" for x in t["worst"])
            + ".",
            "",
        ]
    if not d and not t:
        lines += ["No evaluation results yet.", ""]
    lines.append("Details: [`eval/results/`](eval/results/).")
    return "\n".join(lines)


def main() -> None:
    s = summarize()
    ABOUT.parent.mkdir(parents=True, exist_ok=True)
    ABOUT.write_text(json.dumps(s, indent=2) + "\n")
    readme = README.read_text()
    section = f"{START}\n{markdown(s)}\n{END}"
    if START in readme:
        readme = re.sub(re.escape(START) + ".*?" + re.escape(END), section, readme, flags=re.S)
    else:
        readme = readme.replace("## Development", f"{section}\n\n## Development", 1)
    README.write_text(readme)
    print(f"wrote {ABOUT.relative_to(ROOT)} and the README evaluation section")


if __name__ == "__main__":
    main()

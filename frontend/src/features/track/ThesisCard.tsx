import type { TrackDetail } from "../../api/types";
import { AGREEMENT_LABELS, agreement } from "../map/colors";
import { signed, THESIS_FEATURES } from "./format";

/** The 2007 thesis verdict next to the 2026 model's, with the five thesis features. */
export function ThesisCard({ track }: { track: TrackDetail }) {
  const thesis = track.thesis_2007;
  if (!thesis || !track.octant || track.valence == null || track.arousal == null) return null;
  const verdict = agreement(track.octant, thesis.octant);
  return (
    <section className="card thesis" aria-label="2007 vs 2026">
      <h2>2007 thesis vs 2026 model</h2>
      <dl className="verdicts">
        <div>
          <dt>2007 decision tree</dt>
          <dd>
            <strong>{thesis.octant}</strong> <span className="secondary">“{thesis.hevner}”</span>
          </dd>
        </div>
        <div>
          <dt>2026 model</dt>
          <dd>
            <strong>{track.octant}</strong>{" "}
            <span className="secondary num">
              V {signed(track.valence)} · A {signed(track.arousal)}
            </span>
          </dd>
        </div>
      </dl>
      <p className="secondary">{AGREEMENT_LABELS[verdict]}.</p>
      <ul className="thesis-features">
        {THESIS_FEATURES.map((f) => {
          const value = thesis.features[f.key];
          return (
            <li key={f.key}>
              <span className="bar-label">{f.label}</span>
              <span className="bar-track" title={`threshold ${f.threshold}`}>
                <span className="bar-fill" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
                <span className="threshold" style={{ left: `${f.threshold}%` }} />
              </span>
              <span className="bar-value">
                <span className="num">{value.toFixed(0)}</span> {value >= f.threshold ? f.high : f.low}
              </span>
            </li>
          );
        })}
      </ul>
      <p className="muted small">
        Features re-derived from audio with Essentia (the 2007 CLAM and Echo Nest analyzers no longer
        exist), on the thesis's 0–100 scales; the marker is the tree's threshold. See{" "}
        <a href="https://github.com/circuitflow/moody/blob/main/legacy/README.md" target="_blank" rel="noreferrer">
          known issues in the 2007 system
        </a>
        .
      </p>
    </section>
  );
}

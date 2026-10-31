import { scaleLinear } from "d3-scale";
import type { Segment } from "../../api/types";

const S = 220;
const PAD = 28; // room for the outer labels (e.g. "Displeasure")
const OCTANTS = ["Pleasure", "Excitement", "Arousal", "Distress", "Displeasure", "Depression", "Sleepiness", "Relaxation"];

/** Where the track sits on the full circumplex, with its path through the song. */
export function MiniCircumplex({
  valence,
  arousal,
  segments,
  current,
}: {
  valence: number;
  arousal: number;
  segments: Segment[];
  current: number | null; // segment index under the playhead
}) {
  const s = scaleLinear().domain([-1.1, 1.1]).range([0, S]);
  const sy = scaleLinear().domain([-1.1, 1.1]).range([S, 0]);
  const path = segments.map((p, i) => `${i ? "L" : "M"}${s(p.valence).toFixed(1)},${sy(p.arousal).toFixed(1)}`).join("");
  const at = current !== null && current >= 0 ? segments[current] : undefined;
  return (
    <svg viewBox={`${-PAD} 0 ${S + 2 * PAD} ${S}`} className="mini-circumplex" role="img" aria-label="Position on the mood circle">
      {Array.from({ length: 8 }, (_, k) => {
        const a = ((22.5 + 45 * k) * Math.PI) / 180;
        return <line key={k} className="grid" x1={s(0)} y1={sy(0)} x2={s(1.1 * Math.cos(a))} y2={sy(1.1 * Math.sin(a))} />;
      })}
      <circle className="grid" cx={s(0)} cy={sy(0)} r={s(1) - s(0)} fill="none" />
      {OCTANTS.map((name, k) => {
        const a = (k * 45 * Math.PI) / 180;
        return (
          <text key={name} className="tick" x={s(0.82 * Math.cos(a))} y={sy(0.82 * Math.sin(a))} textAnchor="middle" dominantBaseline="middle">
            {name}
          </text>
        );
      })}
      <path d={path} className="mood-path" />
      <circle cx={s(valence)} cy={sy(arousal)} r={5} className="mean-dot" />
      {at && <circle cx={s(at.valence)} cy={sy(at.arousal)} r={4} className="now-dot" />}
    </svg>
  );
}

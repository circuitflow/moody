/**
 * Mean valence and arousal per bucket (week or hour): two series on one shared axis (same
 * units), 2 px lines broken where a bucket has no matched plays, a legend plus direct end labels,
 * a crosshair readout, and a table view.
 */
import { scaleLinear } from "d3-scale";
import { useState, type PointerEvent } from "react";
import type { MoodBucket } from "../../api/types";
import { gappedPath, lastWithData, moodDomain } from "./geometry";

const W = 960;
const H = 240;
const M = { top: 12, right: 72, bottom: 26, left: 40 };
type Key = "valence" | "arousal";

const signed = (x: number) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(2);

interface Props {
  title: string;
  points: MoodBucket[];
  /** Short label for an axis tick (`first` is the leftmost one). */
  tickLabel: (key: string, first: boolean) => string;
  /** Full label for the readout and the table, e.g. "Week of Apr 27, 2026". */
  label: (key: string) => string;
  /** Indices to label on the x axis. */
  ticks: number[];
}

export function MoodLines({ title, points, tickLabel, label, ticks }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const n = points.length;
  if (n === 0) return null;
  const x = scaleLinear().domain([0, Math.max(1, n - 1)]).range([M.left, W - M.right]);
  const y = scaleLinear().domain(moodDomain(points)).range([H - M.bottom, M.top]).nice();
  const xy = (key: Key) =>
    points.map((p, i) => (p[key] == null ? null : ([x(i), y(p[key]!)] as const)));
  // Lone points (no neighbor with data) would be invisible as a line, so they get a dot.
  const lone = points.flatMap((p, i) =>
    p.valence != null && points[i - 1]?.valence == null && points[i + 1]?.valence == null ? [i] : [],
  );
  const lastIdx = lastWithData(points);
  const last = lastIdx >= 0 ? points[lastIdx]! : null;
  const yTicks = y.ticks(4);

  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    setHover(Math.max(0, Math.min(n - 1, Math.round(x.invert(px)))));
  };
  const h = hover !== null ? points[hover]! : null;

  return (
    <figure className="chart history-chart" aria-label={title}>
      <ul className="legend-row" aria-label="Series">
        <li><span className="line-key" style={{ background: "var(--series-1)" }} /> Valence</li>
        <li><span className="line-key" style={{ background: "var(--series-2)" }} /> Arousal</li>
      </ul>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="trajectory"
        role="img"
        aria-label={`${title}: mean valence and arousal of matched plays. A table follows.`}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        {yTicks.map((v) => (
          <line key={v} className={v === 0 ? "baseline" : "grid"} x1={M.left} x2={W - M.right} y1={y(v)} y2={y(v)} />
        ))}
        {yTicks.map((v) => (
          <text key={v} className="tick num" x={M.left - 6} y={y(v)} textAnchor="end" dominantBaseline="middle">
            {v === 0 ? "0" : signed(v).replace(/0+$/, "").replace(/\.$/, "")}
          </text>
        ))}
        {ticks.map((i, k) => (
          <text key={i} className="tick num" x={x(i)} y={H - 8} textAnchor="middle">
            {tickLabel(points[i]!.key, k === 0)}
          </text>
        ))}
        <path d={gappedPath(xy("valence"))} className="series" style={{ stroke: "var(--series-1)" }} />
        <path d={gappedPath(xy("arousal"))} className="series" style={{ stroke: "var(--series-2)" }} />
        {lone.map((i) => (
          <g key={i}>
            <circle cx={x(i)} cy={y(points[i]!.valence!)} r={4} className="dot" style={{ fill: "var(--series-1)" }} />
            <circle cx={x(i)} cy={y(points[i]!.arousal!)} r={4} className="dot" style={{ fill: "var(--series-2)" }} />
          </g>
        ))}
        {last && (
          <>
            <text className="end-label" x={x(lastIdx) + 6} y={y(last.valence!)} dominantBaseline="middle">
              Valence
            </text>
            <text
              className="end-label"
              x={x(lastIdx) + 6}
              y={y(last.arousal!) + (Math.abs(y(last.arousal!) - y(last.valence!)) < 12 ? 12 : 0)}
              dominantBaseline="middle"
            >
              Arousal
            </text>
          </>
        )}
        {hover !== null && <line className="crosshair" x1={x(hover)} x2={x(hover)} y1={M.top} y2={H - M.bottom} />}
      </svg>
      {h && (
        <div className="readout num" role="status">
          <strong>{label(h.key)}</strong>
          {h.valence != null ? (
            <>
              <span><span className="line-key" style={{ background: "var(--series-1)" }} /> <strong>{signed(h.valence)}</strong> valence</span>
              <span><span className="line-key" style={{ background: "var(--series-2)" }} /> <strong>{signed(h.arousal!)}</strong> arousal</span>
            </>
          ) : (
            <span className="muted">no matched plays</span>
          )}
          <span className="muted">
            {h.matched} of {h.plays} plays matched
          </span>
        </div>
      )}
      <details className="table-view">
        <summary>Show as table</summary>
        <table>
          <thead>
            <tr>
              <th scope="col">{title.includes("hour") ? "Hour" : "Week of"}</th>
              <th scope="col">Valence</th>
              <th scope="col">Arousal</th>
              <th scope="col">Matched plays</th>
              <th scope="col">All plays</th>
            </tr>
          </thead>
          <tbody>
            {points.map((p) => (
              <tr key={p.key}>
                <th scope="row">{label(p.key)}</th>
                <td className="num">{p.valence == null ? "–" : signed(p.valence)}</td>
                <td className="num">{p.arousal == null ? "–" : signed(p.arousal)}</td>
                <td className="num">{p.matched}</td>
                <td className="num">{p.plays}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}

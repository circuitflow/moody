/**
 * Valence and arousal over the track: two series on one shared -1..1 axis (same units), 2 px
 * lines, a legend plus direct end labels, a crosshair readout, the audio playhead, click to seek.
 */
import { scaleLinear } from "d3-scale";
import { useState, type PointerEvent } from "react";
import type { Segment } from "../../api/types";
import { clock, segmentAt, signed } from "./format";

const W = 640;
const H = 220;
const M = { top: 12, right: 72, bottom: 26, left: 36 };

export function TrajectoryChart({
  segments,
  duration,
  playhead,
  onSeek,
}: {
  segments: Segment[];
  duration: number | null;
  playhead: number | null;
  onSeek?: (t: number) => void;
}) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  if (segments.length === 0) return <p className="muted">No mood trajectory for this track.</p>;
  const end = Math.max(duration ?? 0, segments[segments.length - 1]!.start_s + 1.5);
  const x = scaleLinear().domain([0, end]).range([M.left, W - M.right]);
  const y = scaleLinear().domain([-1, 1]).range([H - M.bottom, M.top]);
  const starts = segments.map((s) => s.start_s);
  const path = (key: "valence" | "arousal") =>
    segments.map((s, i) => `${i ? "L" : "M"}${x(s.start_s).toFixed(1)},${y(s[key]).toFixed(1)}`).join("");
  const last = segments[segments.length - 1]!;
  const ticks = x.ticks(6);

  const toTime = (e: PointerEvent<SVGSVGElement> | React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    return Math.min(end, Math.max(0, x.invert(px)));
  };
  const hover = hoverIdx !== null ? segments[hoverIdx]! : null;

  return (
    <figure className="chart" aria-label="Mood over time">
      <ul className="legend-row" aria-label="Series">
        <li><span className="line-key" style={{ background: "var(--series-1)" }} /> Valence</li>
        <li><span className="line-key" style={{ background: "var(--series-2)" }} /> Arousal</li>
      </ul>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="trajectory"
        role="img"
        aria-label={`Valence and arousal over ${clock(end)}`}
        onPointerMove={(e) => setHoverIdx(segmentAt(starts, toTime(e)))}
        onPointerLeave={() => setHoverIdx(null)}
        onClick={(e) => onSeek?.(toTime(e))}
        style={{ cursor: onSeek ? "pointer" : "default" }}
      >
        {[-1, -0.5, 0.5, 1].map((v) => (
          <line key={v} className="grid" x1={M.left} x2={W - M.right} y1={y(v)} y2={y(v)} />
        ))}
        <line className="baseline" x1={M.left} x2={W - M.right} y1={y(0)} y2={y(0)} />
        {[-1, 0, 1].map((v) => (
          <text key={v} className="tick" x={M.left - 6} y={y(v)} textAnchor="end" dominantBaseline="middle">
            {v === 0 ? "0" : signed(v, 0)}
          </text>
        ))}
        {ticks.map((t) => (
          <text key={t} className="tick num" x={x(t)} y={H - 8} textAnchor="middle">
            {clock(t)}
          </text>
        ))}
        <path d={path("valence")} className="series" style={{ stroke: "var(--series-1)" }} />
        <path d={path("arousal")} className="series" style={{ stroke: "var(--series-2)" }} />
        <text className="end-label" x={x(last.start_s) + 6} y={y(last.valence)} dominantBaseline="middle">
          Valence
        </text>
        <text className="end-label" x={x(last.start_s) + 6} y={y(last.arousal) + (Math.abs(last.arousal - last.valence) < 0.12 ? 12 : 0)} dominantBaseline="middle">
          Arousal
        </text>
        {playhead !== null && (
          <line className="playhead" x1={x(playhead)} x2={x(playhead)} y1={M.top} y2={H - M.bottom} />
        )}
        {hover && (
          <line className="crosshair" x1={x(hover.start_s)} x2={x(hover.start_s)} y1={M.top} y2={H - M.bottom} />
        )}
      </svg>
      {hover && (
        <div className="readout num" role="status">
          <strong>{clock(hover.start_s)}</strong>
          <span><span className="line-key" style={{ background: "var(--series-1)" }} /> <strong>{signed(hover.valence)}</strong> valence</span>
          <span><span className="line-key" style={{ background: "var(--series-2)" }} /> <strong>{signed(hover.arousal)}</strong> arousal</span>
        </div>
      )}
    </figure>
  );
}

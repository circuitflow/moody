/**
 * SVG drawn over the mood map on the path page: the target line (dashed), the route through the
 * chosen tracks with their positions numbered, and draggable start/end/via handles.
 */
import { useRef, type KeyboardEvent, type PointerEvent } from "react";
import type { OverlayContext } from "../map/MoodMapView";
import { round } from "./anchors";
import { placeLabels } from "./labels";
import type { Point } from "./planner";

export type HandleKey = "start" | "end" | "via";

export interface HandleSpec {
  key: HandleKey;
  label: string;
  point: Point;
}

interface Props {
  ctx: OverlayContext;
  waypoints: readonly Point[];
  route: readonly Point[];
  handles: readonly HandleSpec[];
  /** `final` is false while dragging and true on release or a key press. */
  onMove: (key: HandleKey, point: Point, final: boolean) => void;
}

const clamp = (x: number) => round(Math.max(-1, Math.min(1, x)));
const signed = (x: number) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(2);

export function PathOverlay({ ctx, waypoints, route, handles, onMove }: Props) {
  const { x, y } = ctx;
  const line = (pts: readonly Point[]) => pts.map((p) => `${x(p[0])},${y(p[1])}`).join(" ");
  const labels = placeLabels(route.map((p) => [x(p[0]), y(p[1])] as const));
  return (
    <g className="path-overlay">
      {waypoints.length > 1 && <polyline className="path-target" points={line(waypoints)} />}
      {route.length > 1 && <polyline className="path-route" points={line(route)} />}
      <g className="path-numbers" aria-hidden="true">
        {labels.map((l, i) => (
          <text key={i} x={l.x} y={l.y} textAnchor={l.anchor}>
            {i + 1}
          </text>
        ))}
      </g>
      {handles.map((h) => (
        <Handle key={h.key} ctx={ctx} spec={h} onMove={onMove} />
      ))}
    </g>
  );
}

function Handle({ ctx, spec, onMove }: { ctx: OverlayContext; spec: HandleSpec; onMove: Props["onMove"] }) {
  const dragging = useRef(false);
  const toPoint = (e: PointerEvent<SVGGElement>): Point => {
    const rect = e.currentTarget.ownerSVGElement!.getBoundingClientRect();
    return [clamp(ctx.x.invert(e.clientX - rect.left)), clamp(ctx.y.invert(e.clientY - rect.top))];
  };
  const onKeyDown = (e: KeyboardEvent<SVGGElement>) => {
    const step = e.shiftKey ? 0.1 : 0.02;
    const [v, a] = spec.point;
    const moves: Record<string, Point> = {
      ArrowLeft: [v - step, a],
      ArrowRight: [v + step, a],
      ArrowUp: [v, a + step],
      ArrowDown: [v, a - step],
    };
    const next = moves[e.key];
    if (!next) return;
    e.preventDefault();
    onMove(spec.key, [clamp(next[0]), clamp(next[1])], true);
  };
  const [px, py] = [ctx.x(spec.point[0]), ctx.y(spec.point[1])];
  return (
    <g
      className={`path-handle path-handle-${spec.key}`}
      data-no-zoom=""
      transform={`translate(${px},${py})`}
      tabIndex={0}
      role="button"
      aria-roledescription="draggable point"
      aria-label={`${spec.label}: valence ${signed(spec.point[0])}, arousal ${signed(spec.point[1])}. Arrow keys move it.`}
      onPointerDown={(e) => {
        e.stopPropagation();
        e.currentTarget.setPointerCapture?.(e.pointerId);
        dragging.current = true;
      }}
      onPointerMove={(e) => {
        e.stopPropagation();
        if (dragging.current) onMove(spec.key, toPoint(e), false);
      }}
      onPointerUp={(e) => {
        e.stopPropagation();
        if (!dragging.current) return;
        dragging.current = false;
        onMove(spec.key, toPoint(e), true);
      }}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={onKeyDown}
    >
      {/* Hit area over the dot and its label, so pressing anywhere on the handle drags it. */}
      <rect x={-14} y={-28} width={64} height={42} rx={6} className="path-handle-hit" />
      <circle r={8} className="path-handle-dot" />
      <text x={12} y={-12}>
        {spec.label}
      </text>
    </g>
  );
}

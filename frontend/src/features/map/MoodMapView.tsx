/**
 * The mood map: canvas for the points (thousands stay fast), an SVG overlay for octant wedges,
 * labels and axes, d3-zoom for pan/zoom, a quadtree for nearest-point hover, and shift-drag lasso.
 */
import { select } from "d3-selection";
import { zoom as d3zoom, zoomIdentity, type ZoomBehavior, type ZoomTransform } from "d3-zoom";
import type { ScaleLinear } from "d3-scale";
import { useEffect, useMemo, useRef, useState, type PointerEvent, type ReactNode } from "react";
import type { MoodMap } from "../../api/types";
import { AGREEMENT_TOKENS, readTokens, SEQ_STEPS, type Agreement } from "./colors";
import {
  fitDomain,
  FULL_DOMAIN,
  makeScales,
  OCTANT_BOUNDARIES_DEG,
  rayInterval,
  type Box,
} from "./geometry";
import { selectInPolygon, type Polygon } from "./lasso";
import { buildIndex, nearest, type ScreenPoint } from "./pick";

/** What an overlay needs to draw in map coordinates. */
export interface OverlayContext {
  x: ScaleLinear<number, number>;
  y: ScaleLinear<number, number>;
  width: number;
  height: number;
}

export type PointColors =
  | { kind: "single" }
  | { kind: "sequential"; colorOf: (row: number) => string | null } // returns a --seq-* token
  | { kind: "categorical"; categoryOf: (row: number) => Agreement };

const OCTANTS = [
  "Pleasure", "Excitement", "Arousal", "Distress",
  "Displeasure", "Depression", "Sleepiness", "Relaxation",
];
const TOKENS = [
  "--surface", "--ink", "--ink-2", "--muted", "--series-1", "--series-2", "--series-3",
  ...SEQ_STEPS,
];

interface Props {
  map: MoodMap;
  visible: readonly boolean[];
  colors: PointColors;
  selection: ReadonlySet<number>;
  onSelect: (ids: Set<number>) => void;
  onOpen: (id: number) => void;
  domainMode: "fit" | "full";
  resetKey: number; // bump to reset zoom
  /** Shift-drag lasso selection (default on). */
  lasso?: boolean;
  /** Extra SVG drawn above the points. Elements marked `data-no-zoom` can be dragged. */
  overlay?: (ctx: OverlayContext) => ReactNode;
}

export function MoodMapView({
  map,
  visible,
  colors,
  selection,
  onSelect,
  onOpen,
  domainMode,
  resetKey,
  lasso: lassoEnabled = true,
  overlay,
}: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const zoomRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const [size, setSize] = useState({ w: 640, h: 560 });
  const [transform, setTransform] = useState<ZoomTransform>(zoomIdentity);
  const [hover, setHover] = useState<ScreenPoint | null>(null);
  const [lasso, setLasso] = useState<Polygon | null>(null);
  const [themeTick, setThemeTick] = useState(0);
  const sizeRef = useRef(size);
  useEffect(() => {
    sizeRef.current = size;
  }, [size]);

  // Size follows the container; the map stays square-ish.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      const w = Math.max(280, Math.floor(entry!.contentRect.width));
      setSize({ w, h: Math.min(w, 640) });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Redraw when the theme changes (tokens are read from CSS at draw time).
  useEffect(() => {
    const observer = new MutationObserver(() => setThemeTick((t) => t + 1));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    const onChange = () => setThemeTick((t) => t + 1);
    media?.addEventListener?.("change", onChange);
    return () => {
      observer.disconnect();
      media?.removeEventListener?.("change", onChange);
    };
  }, []);

  // Pan/zoom on the overlay; shift-drag is reserved for the lasso.
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const behavior = d3zoom<SVGSVGElement, unknown>()
      // Explicit extent: the default reads SVG baseVal, which some environments lack.
      .extent(() => [
        [0, 0],
        [sizeRef.current.w, sizeRef.current.h],
      ])
      .scaleExtent([0.5, 40])
      .filter(
        (event: MouseEvent | WheelEvent) =>
          !event.shiftKey &&
          !(event as MouseEvent).button &&
          !(event.target as Element | null)?.closest?.("[data-no-zoom]"),
      )
      .on("zoom", (event: { transform: ZoomTransform }) => setTransform(event.transform));
    zoomRef.current = behavior;
    select(svg).call(behavior);
    return () => {
      select(svg).on(".zoom", null);
    };
  }, []);

  useEffect(() => {
    const svg = svgRef.current;
    if (svg && zoomRef.current) select(svg).call(zoomRef.current.transform, zoomIdentity);
  }, [resetKey, domainMode]);

  const domain = useMemo(
    () => (domainMode === "full" ? FULL_DOMAIN : fitDomain(map.valence, map.arousal)),
    [map, domainMode],
  );
  const scales = useMemo(() => {
    const base = makeScales(domain, size.w, size.h);
    return { x: transform.rescaleX(base.x), y: transform.rescaleY(base.y) };
  }, [domain, size, transform]);

  const points = useMemo(
    () =>
      map.id.map((_, i) => ({ index: i, x: scales.x(map.valence[i]!), y: scales.y(map.arousal[i]!) })),
    [map, scales],
  );
  const index = useMemo(() => buildIndex(points.filter((p) => visible[p.index])), [points, visible]);
  const selectedRows = useMemo(
    () => new Set(map.id.flatMap((id, i) => (selection.has(id) ? [i] : []))),
    [map, selection],
  );

  // Draw the points.
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size.w * dpr;
    canvas.height = size.h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size.w, size.h);
    const t = readTokens(canvas, TOKENS);
    const fill = (row: number): string => {
      if (colors.kind === "sequential") return t[colors.colorOf(row) ?? "--muted"]!;
      if (colors.kind === "categorical") return t[AGREEMENT_TOKENS[colors.categoryOf(row)]]!;
      return t["--series-1"]!;
    };
    const dot = (p: ScreenPoint, r: number, color: string, ring: string, ringWidth = 2) => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.lineWidth = ringWidth;
      ctx.strokeStyle = ring;
      ctx.stroke();
    };
    // Filtered-out tracks stay as faint context.
    ctx.globalAlpha = 0.35;
    for (const p of points) if (!visible[p.index]) dot(p, 2, t["--muted"]!, t["--surface"]!, 0);
    ctx.globalAlpha = 1;
    for (const p of points) if (visible[p.index]) dot(p, 4, fill(p.index), t["--surface"]!);
    for (const p of points) if (selectedRows.has(p.index)) dot(p, 5, fill(p.index), t["--ink"]!);
    if (hover) dot(hover, 6, fill(hover.index), t["--ink"]!);
  }, [points, visible, colors, selectedRows, hover, size, themeTick]);

  const box: Box = {
    xmin: scales.x.invert(0),
    xmax: scales.x.invert(size.w),
    ymin: scales.y.invert(size.h),
    ymax: scales.y.invert(0),
  };
  const ox = scales.x(0);
  const oy = scales.y(0);
  const far = 4; // V/A units: long enough to leave any zoomed view

  const local = (e: PointerEvent<SVGSVGElement>): [number, number] => {
    const rect = e.currentTarget.getBoundingClientRect();
    return [e.clientX - rect.left, e.clientY - rect.top];
  };

  const onPointerDown = (e: PointerEvent<SVGSVGElement>) => {
    if (!e.shiftKey || !lassoEnabled) return;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    setLasso([local(e)]);
    setHover(null);
  };
  const onPointerMove = (e: PointerEvent<SVGSVGElement>) => {
    const [x, y] = local(e);
    if (lasso) {
      setLasso([...lasso, [x, y]]);
      return;
    }
    setHover(nearest(index, x, y));
  };
  const onPointerUp = () => {
    if (!lasso) return;
    const rows = selectInPolygon(points.filter((p) => visible[p.index]), lasso);
    if (rows.length) onSelect(new Set(rows.map((r) => map.id[r]!)));
    setLasso(null);
  };
  const onClick = (e: PointerEvent<SVGSVGElement> | React.MouseEvent<SVGSVGElement>) => {
    if (e.shiftKey || !hover) return;
    onOpen(map.id[hover.index]!);
  };

  const shown = visible.filter(Boolean).length;
  return (
    <div ref={wrapRef} className="mood-map" style={{ height: size.h }}>
      <canvas
        ref={canvasRef}
        style={{ width: size.w, height: size.h }}
        role="img"
        aria-label={`Mood map: ${shown} of ${map.id.length} tracks by valence (horizontal) and arousal (vertical). The List view has the same tracks as a table.`}
      />
      <svg
        ref={svgRef}
        width={size.w}
        height={size.h}
        className="mood-map-overlay"
        data-testid="map-overlay"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={() => !lasso && setHover(null)}
        onClick={onClick}
        style={{ cursor: hover ? "pointer" : lasso ? "crosshair" : "grab" }}
      >
        <g className="wedges">
          {OCTANT_BOUNDARIES_DEG.map((deg) => (
            <line
              key={deg}
              x1={ox}
              y1={oy}
              x2={scales.x(far * Math.cos((deg * Math.PI) / 180))}
              y2={scales.y(far * Math.sin((deg * Math.PI) / 180))}
            />
          ))}
        </g>
        <g className="axes">
          <line x1={0} x2={size.w} y1={oy} y2={oy} />
          <line x1={ox} x2={ox} y1={0} y2={size.h} />
          <text x={size.w - 8} y={oy - 6} textAnchor="end">valence →</text>
          <text x={ox + 6} y={14}>↑ arousal</text>
        </g>
        <g className="octant-labels">
          {OCTANTS.map((name, k) => {
            const hit = rayInterval(box, k * 45);
            if (!hit) return null;
            const t0 = hit[0] + 0.78 * (hit[1] - hit[0]);
            const theta = (k * 45 * Math.PI) / 180;
            return (
              <text
                key={name}
                x={scales.x(t0 * Math.cos(theta))}
                y={scales.y(t0 * Math.sin(theta))}
                textAnchor="middle"
                dominantBaseline="middle"
              >
                {name}
              </text>
            );
          })}
        </g>
        {overlay?.({ x: scales.x, y: scales.y, width: size.w, height: size.h })}
        {lasso && <polygon className="lasso" points={lasso.map((p) => p.join(",")).join(" ")} />}
      </svg>
      {hover && (
        <div
          className="map-tooltip"
          role="tooltip"
          style={{
            left: Math.min(hover.x + 14, size.w - 220),
            top: Math.max(hover.y - 10, 0),
          }}
        >
          <strong>{map.title[hover.index] ?? "Untitled"}</strong>
          <span className="secondary">{map.artist[hover.index] ?? "Unknown artist"}</span>
          <span className="num">
            V {fmt(map.valence[hover.index]!)} · A {fmt(map.arousal[hover.index]!)} ·{" "}
            {map.octant[hover.index]}
          </span>
          {map.tags[hover.index] && <span className="muted">{map.tags[hover.index]}</span>}
        </div>
      )}
    </div>
  );
}

function fmt(x: number) {
  return (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(2);
}

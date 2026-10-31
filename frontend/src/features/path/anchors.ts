/**
 * Path endpoints: an octant name ("Distress") or a "valence,arousal" pair, as they appear in the
 * URL (`#/path?from=Distress&to=-0.12,0.30`).
 */
import type { MoodMap } from "../../api/types";
import { octantIndex } from "../map/geometry";
import type { Point } from "./planner";

export const OCTANT_NAMES = [
  "Pleasure", "Excitement", "Arousal", "Distress",
  "Displeasure", "Depression", "Sleepiness", "Relaxation",
] as const;

export interface PathSearch {
  from?: string;
  to?: string;
  via?: string;
  n?: number;
  s?: number;
}

export const PATH_DEFAULTS = { from: "Distress", to: "Relaxation", n: 20, s: 0.5 } as const;
export const LENGTH_RANGE = [5, 50] as const;

function quantile(sorted: number[], q: number): number {
  if (sorted.length === 0) return 0;
  const i = Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))));
  return sorted[i]!;
}

/**
 * A point in the direction of octant `k` (angle k·45°), as far out as the library's own tracks in
 * that octant reach (their 75th-percentile radius). Predicted moods are compressed toward the
 * middle, so a fixed radius would sit far outside the data.
 */
export function octantAnchor(map: MoodMap, k: number): Point {
  const radius = (i: number) => Math.hypot(map.valence[i]!, map.arousal[i]!);
  const inOctant = map.id
    .map((_, i) => i)
    .filter((i) => octantIndex(map.valence[i]!, map.arousal[i]!) === k)
    .map(radius)
    .sort((a, b) => a - b);
  const all = map.id.map((_, i) => radius(i)).sort((a, b) => a - b);
  const r = inOctant.length ? quantile(inOctant, 0.75) : quantile(all, 0.75) || 0.5;
  const theta = (k * Math.PI) / 4;
  return [round(r * Math.cos(theta)), round(r * Math.sin(theta))];
}

export function round(x: number): number {
  return Math.round(x * 1000) / 1000;
}

const clamp = (x: number) => Math.max(-1, Math.min(1, x));

/** Resolve an endpoint from the URL; null when it is missing or malformed. */
export function resolvePoint(spec: string | undefined, map: MoodMap): Point | null {
  if (!spec) return null;
  const k = OCTANT_NAMES.findIndex((name) => name.toLowerCase() === spec.trim().toLowerCase());
  if (k >= 0) return octantAnchor(map, k);
  const parts = spec.split(",").map((p) => Number(p.trim()));
  if (parts.length !== 2 || parts.some((p) => !Number.isFinite(p))) return null;
  return [clamp(parts[0]!), clamp(parts[1]!)];
}

export function formatPoint(p: Point): string {
  return `${p[0].toFixed(3)},${p[1].toFixed(3)}`;
}

/** Validate raw search params (TanStack Router `validateSearch`). */
export function parsePathSearch(raw: Record<string, unknown>): PathSearch {
  const str = (v: unknown) => (typeof v === "string" && v.length <= 40 ? v : typeof v === "number" ? String(v) : undefined);
  const num = (v: unknown) => {
    const x = typeof v === "number" ? v : typeof v === "string" ? Number(v) : NaN;
    return Number.isFinite(x) ? x : undefined;
  };
  const out: PathSearch = {};
  const from = str(raw.from);
  const to = str(raw.to);
  const via = str(raw.via);
  const n = num(raw.n);
  const s = num(raw.s);
  if (from) out.from = from;
  if (to) out.to = to;
  if (via) out.via = via;
  if (n !== undefined) out.n = Math.round(Math.max(LENGTH_RANGE[0], Math.min(LENGTH_RANGE[1], n)));
  if (s !== undefined) out.s = Math.max(0, Math.min(1, s));
  return out;
}

/** The octant name when `p` is exactly that octant's anchor (so the picker can show it). */
export function anchorName(p: Point, map: MoodMap): string | null {
  for (let k = 0; k < 8; k++) {
    const a = octantAnchor(map, k);
    if (Math.abs(a[0] - p[0]) < 1e-9 && Math.abs(a[1] - p[1]) < 1e-9) return OCTANT_NAMES[k]!;
  }
  return null;
}

/** Pure helpers for the history charts. */
import type { MoodBucket } from "../../api/types";

/** Y domain around the data, always including 0 (above/below neutral is the point). */
export function moodDomain(points: readonly MoodBucket[]): [number, number] {
  const values = points.flatMap((p) => [p.valence, p.arousal]).filter((v): v is number => v != null);
  if (values.length === 0) return [-0.5, 0.5];
  const lo = Math.max(-1, Math.min(-0.2, Math.min(...values) - 0.05));
  const hi = Math.min(1, Math.max(0.2, Math.max(...values) + 0.05));
  return [lo, hi];
}

/** SVG path that breaks at missing values instead of bridging gaps. */
export function gappedPath(points: readonly (readonly [number, number] | null)[]): string {
  let d = "";
  let pen = false;
  for (const p of points) {
    if (!p) {
      pen = false;
      continue;
    }
    d += `${pen ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`;
    pen = true;
  }
  return d;
}

/** Index of the last bucket with matched plays, or -1. */
export function lastWithData(points: readonly MoodBucket[]): number {
  for (let i = points.length - 1; i >= 0; i--) if (points[i]!.valence != null) return i;
  return -1;
}

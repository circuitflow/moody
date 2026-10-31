/**
 * Color by the job it does (dataviz skill): one series by default, a single-hue sequential ramp
 * for a continuous field, and at most 3 categories for "2007 vs 2026" (scatter is an all-pairs
 * form, so only the first three categorical slots are distinguishable).
 */
import { scaleQuantize } from "d3-scale";

export const SEQ_STEPS = ["--seq-1", "--seq-2", "--seq-3", "--seq-4", "--seq-5"] as const;

export interface SequentialLegend {
  colors: string[];
  thresholds: number[]; // upper bound of each bin except the last
  domain: [number, number];
}

/** Five quantized bins over the observed range of the field. */
export function sequential(values: readonly (number | null)[], ramp: readonly string[]) {
  const finite = values.filter((v): v is number => v !== null && Number.isFinite(v));
  const lo = finite.length ? Math.min(...finite) : 0;
  const hi = finite.length ? Math.max(...finite) : 1;
  const scale = scaleQuantize<string>()
    .domain([lo, hi === lo ? lo + 1 : hi])
    .range([...ramp]);
  const legend: SequentialLegend = {
    colors: [...ramp],
    thresholds: scale.thresholds(),
    domain: [lo, hi],
  };
  return { colorOf: (v: number | null) => (v === null ? null : scale(v)), legend };
}

export type Agreement = "same" | "adjacent" | "different" | "none";

const OCTANT_ORDER = [
  "Pleasure", "Excitement", "Arousal", "Distress",
  "Displeasure", "Depression", "Sleepiness", "Relaxation",
];

/** How far the 2007 thesis octant is from the 2026 one, around the circle. */
export function agreement(octant2026: string, octant2007: string | null): Agreement {
  if (!octant2007) return "none";
  const a = OCTANT_ORDER.indexOf(octant2026);
  const b = OCTANT_ORDER.indexOf(octant2007);
  if (a < 0 || b < 0) return "none";
  const d = Math.min(Math.abs(a - b), 8 - Math.abs(a - b));
  return d === 0 ? "same" : d === 1 ? "adjacent" : "different";
}

export const AGREEMENT_TOKENS: Record<Agreement, string> = {
  same: "--series-1",
  adjacent: "--series-3",
  different: "--series-2",
  none: "--muted",
};

export const AGREEMENT_LABELS: Record<Agreement, string> = {
  same: "Same octant",
  adjacent: "Adjacent octant",
  different: "2+ octants apart",
  none: "No 2007 verdict",
};

/** Resolve CSS custom properties to concrete colors (canvas can't use var()). */
export function readTokens(el: Element, names: readonly string[]): Record<string, string> {
  const style = getComputedStyle(el);
  return Object.fromEntries(names.map((n) => [n, style.getPropertyValue(n).trim() || "#888"]));
}

/**
 * Map geometry. Valence and arousal always share one scale (px per unit), so angles on screen
 * are angles in mood space and the octant wedges stay true.
 */
import { scaleLinear, type ScaleLinear } from "d3-scale";

export interface Domain {
  cx: number; // center valence
  cy: number; // center arousal
  half: number; // half-width of the (square) visible domain, in V/A units
}

export const FULL_DOMAIN: Domain = { cx: 0, cy: 0, half: 1.05 };

/** The smallest square around the data (plus padding), so a compressed spread fills the view. */
export function fitDomain(valence: readonly number[], arousal: readonly number[], pad = 0.08): Domain {
  if (valence.length === 0) return FULL_DOMAIN;
  const [vmin, vmax] = [Math.min(...valence), Math.max(...valence)];
  const [amin, amax] = [Math.min(...arousal), Math.max(...arousal)];
  const half = Math.max(vmax - vmin, amax - amin, 0.2) / 2 + pad;
  return { cx: (vmin + vmax) / 2, cy: (amin + amax) / 2, half };
}

export interface Scales {
  x: ScaleLinear<number, number>;
  y: ScaleLinear<number, number>;
}

/** Equal-unit scales mapping `domain` into a width × height box (centered). */
export function makeScales(domain: Domain, width: number, height: number): Scales {
  const side = Math.min(width, height);
  const ox = (width - side) / 2;
  const oy = (height - side) / 2;
  return {
    x: scaleLinear().domain([domain.cx - domain.half, domain.cx + domain.half]).range([ox, ox + side]),
    y: scaleLinear().domain([domain.cy - domain.half, domain.cy + domain.half]).range([oy + side, oy]),
  };
}

/** Boundaries between the 8 octants: rays from the origin at 22.5° + k·45°. */
export const OCTANT_BOUNDARIES_DEG = Array.from({ length: 8 }, (_, k) => 22.5 + 45 * k);

export function octantIndex(valence: number, arousal: number): number {
  const angle = ((Math.atan2(arousal, valence) * 180) / Math.PI + 360) % 360;
  return Math.round(angle / 45) % 8;
}

export interface Box {
  xmin: number;
  xmax: number;
  ymin: number;
  ymax: number;
}

/**
 * Where a ray from the origin at `angleDeg` crosses the visible box, as [tEnter, tExit] in V/A
 * units along the ray, or null if it never does. Used to place octant labels inside the view.
 */
export function rayInterval(box: Box, angleDeg: number): [number, number] | null {
  const dx = Math.cos((angleDeg * Math.PI) / 180);
  const dy = Math.sin((angleDeg * Math.PI) / 180);
  let t0 = 0;
  let t1 = Infinity;
  for (const [d, lo, hi] of [
    [dx, box.xmin, box.xmax],
    [dy, box.ymin, box.ymax],
  ] as const) {
    if (Math.abs(d) < 1e-12) {
      if (lo > 0 || hi < 0) return null;
      continue;
    }
    const a = lo / d;
    const b = hi / d;
    t0 = Math.max(t0, Math.min(a, b));
    t1 = Math.min(t1, Math.max(a, b));
  }
  return t1 > t0 ? [t0, t1] : null;
}

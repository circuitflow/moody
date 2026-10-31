import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { lambdaFor, nearestRows, planPath, waypoints, type Library, type Point } from "./planner";

const dist = (a: Point, b: Point) => Math.hypot(a[0] - b[0], a[1] - b[1]);

function library(
  va: [number, number][],
  artist: (string | null)[],
  style: number[][] | null = null,
  eligible?: boolean[],
): Library {
  return {
    valence: va.map((p) => p[0]),
    arousal: va.map((p) => p[1]),
    artist,
    style: style && { dims: style[0]?.length ?? 0, data: Float32Array.from(style.flat()) },
    eligible,
  };
}

/** Unit length, rounded to float32 like the planner's style vectors. */
const unit = (v: number[]) => {
  const n = Math.hypot(...v);
  return v.map((x) => (n === 0 ? 0 : Math.fround(x / n)));
};

// Arbitraries
const coord = fc.double({ min: -1, max: 1, noNaN: true });
const point = fc.tuple(coord, coord);
const randomLibrary = (minN: number, maxN: number, artists: number) =>
  fc.integer({ min: minN, max: maxN }).chain((n) =>
    fc.record({
      va: fc.array(point, { minLength: n, maxLength: n }),
      artist: fc.array(fc.option(fc.integer({ min: 0, max: artists - 1 }).map((a) => `A${a}`), { freq: 8 }), {
        minLength: n,
        maxLength: n,
      }),
      style: fc.array(fc.array(fc.double({ min: -1, max: 1, noNaN: true }), { minLength: 3, maxLength: 3 }), {
        minLength: n,
        maxLength: n,
      }),
      eligible: fc.array(fc.integer({ min: 0, max: 4 }).map((x) => x > 0), { minLength: n, maxLength: n }),
    }),
  );

describe("waypoints", () => {
  it("are evenly spaced from start to end", () => {
    const w = waypoints([-0.5, 0.5], [0.5, -0.5], null, 5);
    expect(w[0]).toEqual([-0.5, 0.5]);
    expect(w[4]).toEqual([0.5, -0.5]);
    for (let i = 1; i < 5; i++) expect(dist(w[i]!, w[i - 1]!)).toBeCloseTo(Math.SQRT2 / 4, 9);
  });

  it("bend through the via point, still evenly spaced", () => {
    const w = waypoints([-0.6, 0], [0.6, 0], [0, 0.4], 7);
    expect(w[3]![0]).toBeCloseTo(0, 6); // symmetric curve: the middle waypoint is the via point
    expect(w[3]![1]).toBeCloseTo(0.4, 6);
    const gaps = w.slice(1).map((p, i) => dist(p, w[i]!));
    for (const g of gaps) expect(g).toBeCloseTo(gaps[0]!, 2);
  });

  it("handle degenerate lengths", () => {
    expect(waypoints([0, 0], [1, 1], null, 0)).toEqual([]);
    expect(waypoints([0.2, 0.1], [1, 1], null, 1)).toEqual([[0.2, 0.1]]);
    expect(waypoints([0.2, 0.2], [0.2, 0.2], null, 3)).toEqual([
      [0.2, 0.2],
      [0.2, 0.2],
      [0.2, 0.2],
    ]);
  });
});

describe("lambdaFor", () => {
  it("prices a complete change of sound like two waypoint spacings off the path", () => {
    const points: Point[] = [[0, 0], [0.3, 0], [0.6, 0]];
    expect(lambdaFor(points, 1)).toBeCloseTo(0.6 ** 2, 12); // (2 × 0.3)²
    expect(lambdaFor(points, 0.5)).toBeCloseTo(0.18, 12);
    expect(lambdaFor(points, 0)).toBe(0);
  });

  it("keeps weighing sound when the path has no length", () => {
    expect(lambdaFor([[0.1, 0.1], [0.1, 0.1]], 1)).toBeCloseTo(0.1 ** 2, 12);
  });
});

describe("nearestRows", () => {
  it("matches a full sort", () => {
    fc.assert(
      fc.property(fc.array(point, { minLength: 1, maxLength: 80 }), point, fc.integer({ min: 0, max: 90 }), (va, w, m) => {
        const lib = library(va, va.map(() => null));
        const rows = va.map((_, i) => i);
        const d = (r: number) => (va[r]![0] - w[0]) ** 2 + (va[r]![1] - w[1]) ** 2;
        const expected = [...rows].sort((a, b) => d(a) - d(b) || a - b).slice(0, m);
        expect(nearestRows(lib, rows, w, m)).toEqual(expected);
      }),
    );
  });
});

describe("planPath properties", () => {
  it("returns min(length, eligible) distinct eligible tracks, deterministically", () => {
    fc.assert(
      fc.property(randomLibrary(1, 120, 6), point, point, fc.option(point), fc.integer({ min: 0, max: 40 }), fc.double({ min: 0, max: 1, noNaN: true }), (l, start, end, via, length, smoothness) => {
        const lib = library(l.va, l.artist, l.style.map(unit), l.eligible);
        const req = { start, end, via, length, smoothness };
        const opts = { candidates: 25, beamWidth: 8 };
        const plan = planPath(lib, req, opts);
        const eligible = l.eligible.filter(Boolean).length;
        expect(plan.rows).toHaveLength(Math.min(length, eligible));
        expect(new Set(plan.rows).size).toBe(plan.rows.length);
        for (const r of plan.rows) expect(l.eligible[r]).toBe(true);
        expect(planPath(lib, req, opts)).toEqual(plan);
      }),
    );
  });

  it("never repeats an artist within 3 positions unless it reports the rule relaxed", () => {
    fc.assert(
      fc.property(randomLibrary(1, 80, 5), point, point, fc.integer({ min: 1, max: 30 }), (l, start, end, length) => {
        const lib = library(l.va, l.artist, null, l.eligible);
        const plan = planPath(lib, { start, end, length, smoothness: 0 }, { candidates: 20, beamWidth: 8 });
        if (plan.relaxed) return;
        plan.rows.forEach((r, i) => {
          for (let j = Math.max(0, i - 3); j < i; j++) {
            const a = l.artist[r];
            if (a != null) expect(l.artist[plan.rows[j]!]).not.toBe(a);
          }
        });
      }),
    );
  });

  it("finds the exact optimum when the beam is wide enough (checked by brute force)", () => {
    fc.assert(
      fc.property(randomLibrary(1, 6, 3), point, point, fc.integer({ min: 1, max: 4 }), fc.double({ min: 0, max: 1, noNaN: true }), (l, start, end, length, smoothness) => {
        const style = l.style.map(unit);
        const lib = library(l.va, l.artist, style);
        const plan = planPath(lib, { start, end, length, smoothness }, { beamWidth: 100_000, candidates: 100 });
        const best = bruteForce(l.va, l.artist, style, plan.waypoints, lambdaFor(plan.waypoints, smoothness));
        if (best === null) {
          expect(plan.relaxed).toBe(true);
        } else {
          expect(plan.relaxed).toBe(false);
          expect(plan.cost).toBeCloseTo(best, 9);
        }
      }),
      { numRuns: 300 },
    );
  });

  it("approaches the end point step by step on a dense library", () => {
    const grid: [number, number][] = [];
    for (let i = 0; i <= 20; i++) for (let j = 0; j <= 20; j++) grid.push([-1 + i / 10, -1 + j / 10]);
    const lib = library(grid, grid.map(() => null));
    fc.assert(
      fc.property(point, point, fc.integer({ min: 2, max: 15 }), (start, end, length) => {
        // Dense: waypoints at least two grid cells apart, so each has its own nearest track.
        fc.pre(dist(start, end) / (length - 1) >= 0.2);
        const plan = planPath(lib, { start, end, length, smoothness: 0 });
        const toEnd = plan.rows.map((r) => dist(grid[r]!, end));
        for (let i = 1; i < toEnd.length; i++) expect(toEnd[i]!).toBeLessThan(toEnd[i - 1]!);
        plan.rows.forEach((r, i) => expect(dist(grid[r]!, plan.waypoints[i]!)).toBeLessThanOrEqual(0.0708));
      }),
    );
  });
});

describe("planPath choices", () => {
  // Two tracks tie for the second waypoint; only one sounds like the first track.
  const va: [number, number][] = [
    [0, 0],
    [0.5, 0.05],
    [0.5, -0.05],
  ];
  const style = [
    [1, 0],
    [0, 1],
    [1, 0],
  ];

  it("follows the mood line when smoothness is 0", () => {
    const lib = library(va, ["a", "b", "c"], style);
    const plan = planPath(lib, { start: [0, 0], end: [0.5, 0.04], length: 2, smoothness: 0 });
    expect(plan.rows).toEqual([0, 1]);
  });

  it("prefers the track that sounds alike when smoothness is up", () => {
    const lib = library(va, ["a", "b", "c"], style);
    const plan = planPath(lib, { start: [0, 0], end: [0.5, 0.04], length: 2, smoothness: 1 });
    expect(plan.rows).toEqual([0, 2]);
  });

  it("skips an artist heard in the last three tracks", () => {
    const line: [number, number][] = [
      [0, 0],
      [0.1, 0],
      [0.2, 0],
      [0.1, 0.02],
    ];
    const lib = library(line, ["x", "x", "y", "z"]);
    const plan = planPath(lib, { start: [0, 0], end: [0.2, 0], length: 3, smoothness: 0 });
    expect(plan.rows).toEqual([0, 3, 2]);
    expect(plan.relaxed).toBe(false);
  });

  it("looks past the nearest candidates before breaking the artist rule", () => {
    const lib = library([[0, 0], [0.1, 0], [0.5, 0]], ["a", "a", "b"]);
    const plan = planPath(lib, { start: [0, 0], end: [0.1, 0], length: 2, smoothness: 0 }, { candidates: 1 });
    expect(plan.rows).toEqual([0, 2]);
    expect(plan.relaxed).toBe(false);
  });

  it("still fills the playlist from a single artist, and says so", () => {
    const line: [number, number][] = [0, 1, 2, 3].map((i) => [i / 10, 0]);
    const lib = library(line, ["x", "x", "x", "x"]);
    const plan = planPath(lib, { start: [0, 0], end: [0.3, 0], length: 4, smoothness: 0 });
    expect(plan.rows).toEqual([0, 1, 2, 3]);
    expect(plan.relaxed).toBe(true);
  });

  it("handles an empty or fully filtered library", () => {
    expect(planPath(library([], []), { start: [0, 0], end: [1, 1], length: 5, smoothness: 0.5 }).rows).toEqual([]);
    const lib = library([[0, 0]], ["a"], null, [false]);
    expect(planPath(lib, { start: [0, 0], end: [1, 1], length: 5, smoothness: 0.5 }).rows).toEqual([]);
  });
});

/** Lowest cost over every valid ordered selection, or null when the artist rule allows none. */
function bruteForce(
  va: [number, number][],
  artist: (string | null)[],
  style: number[][],
  points: readonly Point[],
  lambda: number,
): number | null {
  let best: number | null = null;
  const seq: number[] = [];
  const visit = (cost: number) => {
    const i = seq.length;
    if (i === points.length) {
      if (best === null || cost < best) best = cost;
      return;
    }
    for (let r = 0; r < va.length; r++) {
      if (seq.includes(r)) continue;
      const a = artist[r];
      if (a != null && seq.slice(-3).some((s) => artist[s] === a)) continue;
      const w = points[i]!;
      let step = (va[r]![0] - w[0]) ** 2 + (va[r]![1] - w[1]) ** 2;
      if (i > 0 && lambda > 0) {
        const p = style[seq[i - 1]!]!;
        step += lambda * (1 - p.reduce((acc, x, d) => acc + x * style[r]![d]!, 0));
      }
      seq.push(r);
      visit(cost + step);
      seq.pop();
    }
  };
  visit(0);
  return best;
}

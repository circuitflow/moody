import { describe, expect, it } from "vitest";
import type { MoodMap } from "../../api/types";
import { anchorName, formatPoint, octantAnchor, parsePathSearch, resolvePoint } from "./anchors";

function map(points: [number, number][]): MoodMap {
  return {
    id: points.map((_, i) => i + 1),
    valence: points.map((p) => p[0]),
    arousal: points.map((p) => p[1]),
    octant: points.map(() => "Pleasure"),
    tag: points.map(() => null),
    tags: points.map(() => ""),
    octant_2007: points.map(() => null),
    title: points.map(() => null),
    artist: points.map(() => null),
  };
}

describe("octant anchors", () => {
  const m = map([
    [0.1, 0],
    [0.2, 0.01],
    [0.3, 0],
    [0.4, -0.01],
    [-0.05, 0.05],
  ]);

  it("point along the octant's angle, as far out as its tracks reach", () => {
    const [v, a] = octantAnchor(m, 0); // Pleasure: radii 0.1 … 0.4, 75th percentile 0.3
    expect(v).toBeCloseTo(0.3, 2);
    expect(a).toBeCloseTo(0, 6);
    const [dv, da] = octantAnchor(m, 3); // Distress (135°): one track at radius ~0.07
    expect(Math.atan2(da, dv) * (180 / Math.PI)).toBeCloseTo(135, 0);
    expect(Math.hypot(dv, da)).toBeCloseTo(Math.hypot(0.05, 0.05), 2);
  });

  it("fall back to the library's spread for an empty octant", () => {
    const [v, a] = octantAnchor(m, 6); // Sleepiness: no tracks
    expect(v).toBeCloseTo(0, 6);
    expect(a).toBeLessThan(-0.2);
  });

  it("resolve names, coordinates and nonsense", () => {
    expect(resolvePoint("pleasure", m)).toEqual(octantAnchor(m, 0));
    expect(resolvePoint("-0.2, 0.35", m)).toEqual([-0.2, 0.35]);
    expect(resolvePoint("5,-9", m)).toEqual([1, -1]);
    expect(resolvePoint("calm", m)).toBeNull();
    expect(resolvePoint("1,2,3", m)).toBeNull();
    expect(resolvePoint(undefined, m)).toBeNull();
    expect(anchorName(octantAnchor(m, 3), m)).toBe("Distress");
    expect(anchorName([0.123, 0.456], m)).toBeNull();
    expect(formatPoint([-0.2, 0.35])).toBe("-0.200,0.350");
  });
});

describe("parsePathSearch", () => {
  it("keeps valid values and clamps the rest", () => {
    expect(parsePathSearch({ from: "Distress", to: "0.1,0.2", n: 200, s: -1 })).toEqual({
      from: "Distress",
      to: "0.1,0.2",
      n: 50,
      s: 0,
    });
    expect(parsePathSearch({ n: "12", s: "0.25", via: { x: 1 } })).toEqual({ n: 12, s: 0.25 });
    expect(parsePathSearch({ from: "x".repeat(100), n: "lots" })).toEqual({});
  });
});

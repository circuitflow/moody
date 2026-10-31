import type { MoodMap } from "../../api/types";
import { NO_FILTERS } from "../../state/filters";
import { agreement, sequential } from "./colors";
import { visibleMask, tagFrequencies } from "./filters";
import { fitDomain, FULL_DOMAIN, makeScales, octantIndex } from "./geometry";
import { selectInPolygon } from "./lasso";
import { buildIndex, nearest } from "./pick";

const map: MoodMap = {
  id: [1, 2, 3],
  valence: [0.5, -0.3, 0.1],
  arousal: [0.4, -0.35, -0.2],
  octant: ["Excitement", "Depression", "Relaxation"],
  tag: ["happy", "sad", "calm"],
  tags: ["happy energetic", "sad", "calm happy"],
  octant_2007: ["Excitement", "Pleasure", null],
  title: ["Up", "Down", "Still"],
  artist: ["A", "B", "A"],
};

test("fitDomain covers every point and keeps a square", () => {
  const d = fitDomain(map.valence, map.arousal);
  for (const [v, a] of map.valence.map((v, i) => [v, map.arousal[i]!])) {
    expect(Math.abs(v! - d.cx)).toBeLessThanOrEqual(d.half);
    expect(Math.abs(a! - d.cy)).toBeLessThanOrEqual(d.half);
  }
  expect(fitDomain([], [])).toEqual(FULL_DOMAIN);
});

test("scales use equal px per unit and put positive arousal up", () => {
  const { x, y } = makeScales(FULL_DOMAIN, 400, 300);
  expect(x(1) - x(0)).toBeCloseTo(y(0) - y(1));
  expect(y(0.5)).toBeLessThan(y(-0.5));
});

test("octantIndex matches the thesis order", () => {
  expect(octantIndex(1, 0)).toBe(0); // Pleasure
  expect(octantIndex(0.5, 0.5)).toBe(1); // Excitement
  expect(octantIndex(0, -1)).toBe(6); // Sleepiness
  expect(octantIndex(0.5, -0.5)).toBe(7); // Relaxation
});

test("nearest picks within the radius only", () => {
  const index = buildIndex([
    { index: 0, x: 10, y: 10 },
    { index: 1, x: 100, y: 100 },
  ]);
  expect(nearest(index, 20, 15)?.index).toBe(0);
  expect(nearest(index, 55, 55)).toBeNull();
});

test("lasso selects points inside the polygon", () => {
  const points = [
    { index: 0, x: 5, y: 5 },
    { index: 1, x: 50, y: 50 },
  ];
  const square: [number, number][] = [[0, 0], [10, 0], [10, 10], [0, 10]];
  expect(selectInPolygon(points, square)).toEqual([0]);
  expect(selectInPolygon(points, [[0, 0], [1, 1]])).toEqual([]);
});

test("filters combine query, tags (any) and octants", () => {
  expect(visibleMask(map, NO_FILTERS)).toEqual([true, true, true]);
  expect(visibleMask(map, { ...NO_FILTERS, query: "a" })).toEqual([true, false, true]); // artist
  expect(visibleMask(map, { ...NO_FILTERS, query: "zzz" })).toEqual([false, false, false]);
  expect(visibleMask(map, { ...NO_FILTERS, query: "st" })).toEqual([false, false, true]);
  expect(visibleMask(map, { ...NO_FILTERS, tags: new Set(["happy"]) })).toEqual([true, false, true]);
  expect(
    visibleMask(map, { ...NO_FILTERS, tags: new Set(["happy"]), octants: new Set(["Relaxation"]) }),
  ).toEqual([false, false, true]);
  expect(tagFrequencies(map)[0]).toEqual(["happy", 2]);
});

test("sequential bins span the observed range", () => {
  const { colorOf, legend } = sequential([0, 5, 10, null], ["a", "b", "c", "d", "e"]);
  expect(legend.domain).toEqual([0, 10]);
  expect(colorOf(0)).toBe("a");
  expect(colorOf(10)).toBe("e");
  expect(colorOf(null)).toBeNull();
  expect(sequential([], ["a"]).legend.domain).toEqual([0, 1]);
});

test("agreement wraps around the circle", () => {
  expect(agreement("Excitement", "Excitement")).toBe("same");
  expect(agreement("Pleasure", "Relaxation")).toBe("adjacent"); // 0 vs 7
  expect(agreement("Pleasure", "Displeasure")).toBe("different");
  expect(agreement("Pleasure", null)).toBe("none");
});

test("rayInterval finds where octant rays cross the view", async () => {
  const { rayInterval } = await import("./geometry");
  const box = { xmin: -1, xmax: 1, ymin: -1, ymax: 1 };
  expect(rayInterval(box, 0)).toEqual([0, 1]);
  const diag = rayInterval(box, 45)!;
  expect(diag[1]).toBeCloseTo(Math.SQRT2);
  // Origin outside the view: only rays heading into it cross.
  const right = { xmin: 0.2, xmax: 0.8, ymin: -0.1, ymax: 0.1 };
  expect(rayInterval(right, 0)).toEqual([0.2, 0.8]);
  expect(rayInterval(right, 180)).toBeNull();
});

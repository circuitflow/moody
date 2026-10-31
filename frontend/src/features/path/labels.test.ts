import { expect, it } from "vitest";
import { placeLabels } from "./labels";

it("puts a lone label at the upper right of its dot", () => {
  expect(placeLabels([[100, 100]])).toEqual([{ x: 106, y: 94, anchor: "start" }]);
});

it("moves a neighbor's label to another side instead of overlapping", () => {
  const [a, b] = placeLabels([
    [100, 100],
    [104, 100],
  ]);
  expect(a).toEqual({ x: 106, y: 94, anchor: "start" });
  expect(b!.anchor === "end" || b!.y > 100).toBe(true);
});

it("never stacks labels when there is room", () => {
  const points: [number, number][] = [
    [50, 50],
    [53, 51],
    [56, 49],
  ];
  const labels = placeLabels(points);
  const keys = labels.map((l) => `${l.x},${l.y},${l.anchor}`);
  expect(new Set(keys).size).toBe(3);
});

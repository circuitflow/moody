import { expect, it } from "vitest";
import type { MoodBucket } from "../../api/types";
import { gappedPath, lastWithData, moodDomain } from "./geometry";

const b = (valence: number | null, arousal: number | null = valence): MoodBucket => ({
  key: "k", plays: 1, matched: valence == null ? 0 : 1, valence, arousal,
});

it("breaks lines at buckets without matched plays", () => {
  expect(gappedPath([[0, 0], [1, 1], null, [3, 3], [4, 4]])).toBe("M0.0,0.0L1.0,1.0M3.0,3.0L4.0,4.0");
  expect(gappedPath([null, null])).toBe("");
});

it("zooms the axis to the data but always shows zero", () => {
  expect(moodDomain([b(0.3, 0.4), b(0.35, 0.45)])).toEqual([-0.2, 0.5]);
  const [lo, hi] = moodDomain([b(-0.6, -0.7)]);
  expect(lo).toBeCloseTo(-0.75);
  expect(hi).toBe(0.2);
  expect(moodDomain([b(null)])).toEqual([-0.5, 0.5]);
  expect(moodDomain([b(0.99, -0.99)])).toEqual([-1, 1]);
});

it("finds the last bucket with data", () => {
  expect(lastWithData([b(0.1), b(0.2), b(null)])).toBe(1);
  expect(lastWithData([b(null)])).toBe(-1);
});

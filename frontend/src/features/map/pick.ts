import { quadtree, type Quadtree } from "d3-quadtree";

export interface ScreenPoint {
  index: number; // row in the MoodMap arrays
  x: number;
  y: number;
}

export function buildIndex(points: ScreenPoint[]): Quadtree<ScreenPoint> {
  return quadtree<ScreenPoint>()
    .x((p) => p.x)
    .y((p) => p.y)
    .addAll(points);
}

/** Nearest point within `radius` px (a generous hit area, not the 8 px dot), or null. */
export function nearest(
  index: Quadtree<ScreenPoint>,
  x: number,
  y: number,
  radius = 24,
): ScreenPoint | null {
  return index.find(x, y, radius) ?? null;
}

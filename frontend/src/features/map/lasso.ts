import { polygonContains } from "d3-polygon";
import type { ScreenPoint } from "./pick";

export type Polygon = [number, number][];

/** Rows whose screen position falls inside the lasso polygon (needs at least 3 vertices). */
export function selectInPolygon(points: readonly ScreenPoint[], polygon: Polygon): number[] {
  if (polygon.length < 3) return [];
  return points.filter((p) => polygonContains(polygon, [p.x, p.y])).map((p) => p.index);
}

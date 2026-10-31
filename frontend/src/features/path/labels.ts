/** Placement of the playlist position numbers next to their dots, avoiding overlaps. */

export interface PlacedLabel {
  x: number;
  y: number;
  anchor: "start" | "end";
}

type Box = [number, number, number, number]; // x0, y0, x1, y1

const DIGIT_W = 7; // px per digit at 11px tabular figures
const HEIGHT = 11;
const GAP = 6;
const DOT = 5;

const overlaps = (a: Box, b: Box) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];

/**
 * For each screen point (in playlist order), the first of four spots around its dot (upper right,
 * upper left, lower right, lower left) that overlaps no placed label and no dot. If none is free,
 * it falls back to upper right.
 */
export function placeLabels(points: readonly (readonly [number, number])[]): PlacedLabel[] {
  const dots: Box[] = points.map(([x, y]) => [x - DOT, y - DOT, x + DOT, y + DOT]);
  const placed: Box[] = [];
  return points.map(([x, y], i) => {
    const w = String(i + 1).length * DIGIT_W;
    const spots: [PlacedLabel, Box][] = [
      [{ x: x + GAP, y: y - GAP, anchor: "start" }, [x + GAP, y - GAP - HEIGHT, x + GAP + w, y - GAP]],
      [{ x: x - GAP, y: y - GAP, anchor: "end" }, [x - GAP - w, y - GAP - HEIGHT, x - GAP, y - GAP]],
      [{ x: x + GAP, y: y + GAP + HEIGHT, anchor: "start" }, [x + GAP, y + GAP, x + GAP + w, y + GAP + HEIGHT]],
      [{ x: x - GAP, y: y + GAP + HEIGHT, anchor: "end" }, [x - GAP - w, y + GAP, x - GAP, y + GAP + HEIGHT]],
    ];
    const free = spots.find(([, box]) => !placed.some((p) => overlaps(p, box)) && !dots.some((d) => overlaps(d, box)));
    const [label, box] = free ?? spots[0]!;
    placed.push(box);
    return label;
  });
}

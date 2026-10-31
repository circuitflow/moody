/**
 * Mood-path planner (spec §8). It picks `length` distinct tracks that walk from a start mood to
 * an end mood. Each track should sit close to its waypoint and sound like the one before:
 *
 *   minimize  Σ ‖va(tᵢ) − wᵢ‖²  +  λ · Σ (1 − cos(style(tᵢ₋₁), style(tᵢ)))
 *
 * It uses a beam search over positions; each waypoint's candidates are its nearest eligible
 * tracks. A pure function over arrays, so it is property-tested and runs unchanged in the
 * static demo.
 */

export type Point = readonly [number, number];

export interface Library {
  valence: ArrayLike<number>;
  arousal: ArrayLike<number>;
  artist: ReadonlyArray<string | null>;
  /** Unit style vectors aligned with the rows (zeros when unknown); null ignores how tracks sound. */
  style: { dims: number; data: Float32Array } | null;
  /** Rows the planner may use (the active filters); every row when omitted. */
  eligible?: readonly boolean[];
}

export interface PathRequest {
  start: Point;
  end: Point;
  /** Optional point the path bends through (a quadratic curve). */
  via?: Point | null;
  length: number;
  /** 0 follows the mood line only; 1 strongly prefers tracks that sound like the previous one. */
  smoothness: number;
}

export interface PlannerOptions {
  /** B: partial playlists kept per step. */
  beamWidth?: number;
  /** M: nearest tracks considered per waypoint. */
  candidates?: number;
  /** k: no artist repeats within this many positions. */
  artistGap?: number;
}

export interface PlannedPath {
  rows: number[];
  waypoints: Point[];
  cost: number;
  /** The artist rule had to be dropped somewhere: too few artists among the eligible tracks. */
  relaxed: boolean;
}

export const DEFAULTS = { beamWidth: 32, candidates: 200, artistGap: 3 } as const;
/** Spacing floor (V/A units) for λ, so a path whose start and end coincide still weighs sound. */
const MIN_SPACING = 0.05;

/**
 * `n` points evenly spaced by arc length from `start` to `end`. With `via`, the path is a
 * quadratic curve that passes through `via` halfway.
 */
export function waypoints(start: Point, end: Point, via: Point | null | undefined, n: number): Point[] {
  if (n <= 0) return [];
  if (n === 1) return [start];
  const at = (t: number): Point => {
    if (!via) return [start[0] + t * (end[0] - start[0]), start[1] + t * (end[1] - start[1])];
    // Control point that makes B(0.5) = via.
    const c = [2 * via[0] - (start[0] + end[0]) / 2, 2 * via[1] - (start[1] + end[1]) / 2];
    const u = 1 - t;
    return [
      u * u * start[0] + 2 * u * t * c[0]! + t * t * end[0],
      u * u * start[1] + 2 * u * t * c[1]! + t * t * end[1],
    ];
  };
  const samples = via ? 512 : 1;
  const pts: Point[] = Array.from({ length: samples + 1 }, (_, i) => at(i / samples));
  const cum = [0];
  for (let i = 1; i < pts.length; i++) {
    cum.push(cum[i - 1]! + Math.hypot(pts[i]![0] - pts[i - 1]![0], pts[i]![1] - pts[i - 1]![1]));
  }
  const total = cum[cum.length - 1]!;
  const out: Point[] = [];
  let seg = 1;
  for (let j = 0; j < n; j++) {
    const target = (total * j) / (n - 1);
    while (seg < cum.length - 1 && cum[seg]! < target) seg++;
    const span = cum[seg]! - cum[seg - 1]!;
    const f = span > 0 ? (target - cum[seg - 1]!) / span : 0;
    const a = pts[seg - 1]!;
    const b = pts[seg]!;
    out.push([a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])]);
  }
  return out;
}

/**
 * λ for a smoothness setting. At smoothness 1, a track that sounds completely different from the
 * previous one (1 − cos = 1) costs as much as one two waypoint spacings off the path.
 */
export function lambdaFor(points: readonly Point[], smoothness: number): number {
  let total = 0;
  for (let i = 1; i < points.length; i++) {
    total += Math.hypot(points[i]![0] - points[i - 1]![0], points[i]![1] - points[i - 1]![1]);
  }
  const spacing = Math.max(points.length > 1 ? total / (points.length - 1) : 0, MIN_SPACING);
  return Math.max(0, smoothness) * (2 * spacing) ** 2;
}

interface Node {
  row: number;
  prev: Node | null;
  cost: number;
  /** Creation order: equal costs keep the earlier node, so results are deterministic. */
  seq: number;
}

export function planPath(lib: Library, req: PathRequest, opts: PlannerOptions = {}): PlannedPath {
  const B = Math.max(1, opts.beamWidth ?? DEFAULTS.beamWidth);
  const M = opts.candidates ?? DEFAULTS.candidates;
  const k = opts.artistGap ?? DEFAULTS.artistGap;
  const total = lib.valence.length;
  const eligibleRows: number[] = [];
  for (let r = 0; r < total; r++) if (lib.eligible?.[r] ?? true) eligibleRows.push(r);
  const n = Math.max(0, Math.min(Math.floor(req.length), eligibleRows.length));
  const points = waypoints(req.start, req.end, req.via, n);
  if (n === 0) return { rows: [], waypoints: points, cost: 0, relaxed: false };
  const style = lib.style && lib.style.dims > 0 ? lib.style : null;
  const lambda = style ? lambdaFor(points, req.smoothness) : 0;

  // Artists as small integers (-1 = unknown, which never clashes).
  const artistIds = new Int32Array(total);
  const idOf = new Map<string, number>();
  for (let r = 0; r < total; r++) {
    const a = lib.artist[r];
    if (a == null) artistIds[r] = -1;
    else {
      if (!idOf.has(a)) idOf.set(a, idOf.size);
      artistIds[r] = idOf.get(a)!;
    }
  }
  const unlike = (a: number, b: number) => {
    if (!style) return 0;
    const { dims, data } = style;
    let dot = 0;
    for (let i = 0, ia = a * dims, ib = b * dims; i < dims; i++) dot += data[ia + i]! * data[ib + i]!;
    return 1 - dot;
  };

  // `stamp[row] === mark` means the row is already in the prefix being extended.
  const stamp = new Int32Array(total);
  let mark = 0;
  let seq = 0;

  const expand = (beam: (Node | null)[], cands: readonly number[], w: Point, artistRule: boolean) => {
    const heap: Node[] = []; // max-heap on (cost, seq): the worst kept node sits on top
    const worse = (a: Node, b: Node) => a.cost > b.cost || (a.cost === b.cost && a.seq > b.seq);
    const fit = cands.map((row) => (lib.valence[row]! - w[0]) ** 2 + (lib.arousal[row]! - w[1]) ** 2);
    for (const node of beam) {
      mark++;
      const recent: number[] = [];
      for (let p = node, depth = 0; p; p = p.prev, depth++) {
        stamp[p.row] = mark;
        if (artistRule && depth < k && artistIds[p.row]! >= 0) recent.push(artistIds[p.row]!);
      }
      const base = node?.cost ?? 0;
      for (let c = 0; c < cands.length; c++) {
        const row = cands[c]!;
        if (stamp[row] === mark) continue;
        if (recent.length && recent.includes(artistIds[row]!)) continue;
        const cost = base + (fit[c]! + (node && lambda ? lambda * unlike(node.row, row) : 0));
        if (heap.length === B && cost >= heap[0]!.cost) continue; // ties keep the earlier node
        const item: Node = { row, prev: node, cost, seq: seq++ };
        if (heap.length < B) {
          heap.push(item);
          for (let i = heap.length - 1; i > 0; ) {
            const parent = (i - 1) >> 1;
            if (!worse(heap[i]!, heap[parent]!)) break;
            [heap[i], heap[parent]] = [heap[parent]!, heap[i]!];
            i = parent;
          }
        } else {
          heap[0] = item;
          for (let i = 0; ; ) {
            const l = 2 * i + 1;
            const r = l + 1;
            let top = i;
            if (l < heap.length && worse(heap[l]!, heap[top]!)) top = l;
            if (r < heap.length && worse(heap[r]!, heap[top]!)) top = r;
            if (top === i) break;
            [heap[i], heap[top]] = [heap[top]!, heap[i]!];
            i = top;
          }
        }
      }
    }
    return heap.sort((a, b) => a.cost - b.cost || a.seq - b.seq);
  };

  let beam: (Node | null)[] = [null];
  let relaxed = false;
  for (const w of points) {
    let next = expand(beam, nearestRows(lib, eligibleRows, w, M), w, true);
    // Fallbacks keep the playlist full length: wider candidates first, then drop the artist rule.
    if (next.length === 0 && M < eligibleRows.length) next = expand(beam, eligibleRows, w, true);
    if (next.length === 0) {
      next = expand(beam, eligibleRows, w, false);
      relaxed = true;
    }
    beam = next;
  }
  const best = beam[0]!;
  const rows: number[] = [];
  for (let p: Node | null = best; p; p = p.prev) rows.push(p.row);
  return { rows: rows.reverse(), waypoints: points, cost: best.cost, relaxed };
}

/** The `m` eligible rows nearest to `w`, nearest first (ties by row). A bounded max-heap: O(n log m). */
export function nearestRows(lib: Library, rows: readonly number[], w: Point, m: number): number[] {
  const heap: [number, number][] = []; // [distance², row], max-heap on (distance, row)
  const above = (a: [number, number], b: [number, number]) => a[0] > b[0] || (a[0] === b[0] && a[1] > b[1]);
  const swap = (i: number, j: number) => ([heap[i], heap[j]] = [heap[j]!, heap[i]!]);
  for (const row of rows) {
    const item: [number, number] = [(lib.valence[row]! - w[0]) ** 2 + (lib.arousal[row]! - w[1]) ** 2, row];
    if (heap.length < m) {
      heap.push(item);
      for (let i = heap.length - 1; i > 0; ) {
        const parent = (i - 1) >> 1;
        if (!above(heap[i]!, heap[parent]!)) break;
        swap(i, parent);
        i = parent;
      }
    } else if (m > 0 && above(heap[0]!, item)) {
      heap[0] = item;
      for (let i = 0; ; ) {
        const l = 2 * i + 1;
        const r = l + 1;
        let top = i;
        if (l < heap.length && above(heap[l]!, heap[top]!)) top = l;
        if (r < heap.length && above(heap[r]!, heap[top]!)) top = r;
        if (top === i) break;
        swap(i, top);
        i = top;
      }
    }
  }
  return heap.sort((a, b) => a[0] - b[0] || a[1] - b[1]).map(([, row]) => row);
}

/** Style vectors re-ordered to match map rows (zeros for tracks without one). */
export function alignStyle(
  mapIds: readonly number[],
  style: { dims: number; data: Float32Array; rowOf: Map<number, number> },
): { dims: number; data: Float32Array } {
  const { dims } = style;
  const data = new Float32Array(mapIds.length * dims);
  mapIds.forEach((id, row) => {
    const src = style.rowOf.get(id);
    if (src !== undefined) data.set(style.data.subarray(src * dims, (src + 1) * dims), row * dims);
  });
  return { dims, data };
}

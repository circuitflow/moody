export type ColorBy =
  | { kind: "none" }
  | { kind: "field"; field: string } // sequential: bpm, loudness or tag:<mood>
  | { kind: "agreement" }; // categorical: 2007 vs 2026 octant

export interface Filters {
  query: string;
  tags: ReadonlySet<string>;
  octants: ReadonlySet<string>;
}

export const NO_FILTERS: Filters = { query: "", tags: new Set(), octants: new Set() };

import { Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { visibleMask } from "../features/map/filters";
import { MapControls } from "../features/map/MapControls";
import { signed } from "../features/track/format";
import { useMeta, useMoodMap } from "../data/hooks";
import { useLibrary } from "../state/library";

type SortKey = "title" | "artist" | "valence" | "arousal" | "octant" | "octant_2007";
const PAGE = 200;

const COLUMNS: { key: SortKey; label: string; numeric?: boolean }[] = [
  { key: "title", label: "Title" },
  { key: "artist", label: "Artist" },
  { key: "valence", label: "Valence", numeric: true },
  { key: "arousal", label: "Arousal", numeric: true },
  { key: "octant", label: "Octant (2026)" },
  { key: "octant_2007", label: "Octant (2007)" },
];

/** The accessible, keyboard-friendly twin of the map: same tracks, same filters, as a table. */
export function ListPage() {
  const meta = useMeta();
  const mapQuery = useMoodMap();
  const { filters, setFilters, selection } = useLibrary();
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "title", dir: 1 });
  const [onlySelected, setOnlySelected] = useState(false);
  const [limit, setLimit] = useState(PAGE);
  const map = mapQuery.data;

  const rows = useMemo(() => {
    if (!map) return [];
    const visible = visibleMask(map, filters);
    const idx = map.id
      .map((_, i) => i)
      .filter((i) => visible[i] && (!onlySelected || selection.has(map.id[i]!)));
    const value = (i: number): string | number => {
      const v = map[sort.key][i];
      return v ?? (sort.key === "valence" || sort.key === "arousal" ? 0 : "");
    };
    return idx.sort((a, b) => {
      const [x, y] = [value(a), value(b)];
      const cmp = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
      return cmp * sort.dir || a - b;
    });
  }, [map, filters, sort, onlySelected, selection]);

  if (mapQuery.isError || meta.isError) return <p role="alert">Could not load the library.</p>;
  if (!map || !meta.data) return <p className="muted">Loading tracks…</p>;

  const toggleSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: 1 }));

  return (
    <section aria-label="Track list">
      <MapControls meta={meta.data} map={map} filters={filters} setFilters={setFilters} />
      <div className="control-row count">
        <span className="num" aria-live="polite">
          Showing {rows.length} of {map.id.length} tracks
        </span>
        {selection.size > 0 && (
          <label>
            <input
              type="checkbox"
              checked={onlySelected}
              onChange={(e) => setOnlySelected(e.target.checked)}
            />{" "}
            Only the {selection.size} selected on the map
          </label>
        )}
      </div>
      <div className="card table-wrap">
        <table className="tracks">
          <thead>
            <tr>
              {COLUMNS.map((c) => (
                <th
                  key={c.key}
                  scope="col"
                  aria-sort={sort.key === c.key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
                  className={c.numeric ? "num right" : undefined}
                >
                  <button type="button" className="sort" onClick={() => toggleSort(c.key)}>
                    {c.label}
                    {sort.key === c.key ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
                  </button>
                </th>
              ))}
              <th scope="col">Top mood tags</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, limit).map((i) => (
              <tr key={map.id[i]} aria-selected={selection.has(map.id[i]!) || undefined}>
                <td>
                  <Link to="/track/$trackId" params={{ trackId: String(map.id[i]) }}>
                    {map.title[i] ?? "Untitled"}
                  </Link>
                </td>
                <td className="secondary">{map.artist[i] ?? "—"}</td>
                <td className="num right">{signed(map.valence[i]!)}</td>
                <td className="num right">{signed(map.arousal[i]!)}</td>
                <td>{map.octant[i]}</td>
                <td className="secondary">{map.octant_2007[i] ?? "—"}</td>
                <td className="muted">{map.tags[i]}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length > limit && (
          <button type="button" className="more" onClick={() => setLimit(limit + PAGE)}>
            Show {Math.min(PAGE, rows.length - limit)} more
          </button>
        )}
      </div>
    </section>
  );
}

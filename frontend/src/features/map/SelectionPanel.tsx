import { Link } from "@tanstack/react-router";
import type { MoodMap } from "../../api/types";

const MAX_LISTED = 50;

export function SelectionPanel({
  map,
  selection,
  onClear,
}: {
  map: MoodMap;
  selection: ReadonlySet<number>;
  onClear: () => void;
}) {
  if (selection.size === 0) {
    return <p className="muted hint">Shift-drag on the map to lasso a group of tracks.</p>;
  }
  const rows = map.id.flatMap((id, i) => (selection.has(id) ? [i] : []));
  return (
    <aside className="card selection" aria-label="Selected tracks">
      <div className="selection-head">
        <strong>{selection.size} selected</strong>
        <button type="button" onClick={onClear}>
          Clear
        </button>
      </div>
      <ol>
        {rows.slice(0, MAX_LISTED).map((i) => (
          <li key={map.id[i]}>
            <Link to="/track/$trackId" params={{ trackId: String(map.id[i]) }}>
              {map.title[i] ?? "Untitled"}
            </Link>{" "}
            <span className="secondary">{map.artist[i] ?? ""}</span>
          </li>
        ))}
      </ol>
      {rows.length > MAX_LISTED && <p className="muted">and {rows.length - MAX_LISTED} more</p>}
    </aside>
  );
}

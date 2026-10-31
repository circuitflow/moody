import type { Meta, MoodMap } from "../../api/types";
import { NO_FILTERS, type ColorBy, type Filters } from "../../state/filters";
import { tagFrequencies } from "./filters";

const TOP_TAG_CHIPS = 10;

function toggle<T>(set: ReadonlySet<T>, item: T): Set<T> {
  const next = new Set(set);
  if (next.has(item)) next.delete(item);
  else next.add(item);
  return next;
}

export interface MapOnlyControls {
  colorBy: ColorBy;
  setColorBy: (c: ColorBy) => void;
  domainMode: "fit" | "full";
  setDomainMode: (m: "fit" | "full") => void;
  onResetZoom: () => void;
}

interface Props {
  meta: Meta;
  map: MoodMap;
  filters: Filters;
  setFilters: (f: Filters) => void;
  /** Color-by and view buttons; omitted in the list view, which shares the filters. */
  mapOptions?: MapOnlyControls;
}

export function MapControls({ meta, map, filters, setFilters, mapOptions }: Props) {
  const frequent = tagFrequencies(map);
  const chips = frequent.slice(0, TOP_TAG_CHIPS).map(([t]) => t);
  const others = frequent.slice(TOP_TAG_CHIPS).map(([t]) => t);
  const colorBy = mapOptions?.colorBy;
  const colorValue =
    colorBy?.kind === "field" ? colorBy.field : colorBy?.kind === "agreement" ? "agreement" : "none";
  const dirty = filters.query || filters.tags.size || filters.octants.size;

  return (
    <div className="map-controls" role="group" aria-label="Map filters">
      <div className="control-row">
        <input
          type="search"
          placeholder="Search title or artist"
          aria-label="Search title or artist"
          value={filters.query}
          onChange={(e) => setFilters({ ...filters, query: e.target.value })}
        />
        {mapOptions && (
          <>
            <label>
              Color by{" "}
              <select
                value={colorValue}
                onChange={(e) => {
                  const v = e.target.value;
                  mapOptions.setColorBy(v === "none" ? { kind: "none" } : v === "agreement" ? { kind: "agreement" } : { kind: "field", field: v });
                }}
              >
                <option value="none">Nothing (one color)</option>
                <option value="agreement">2007 vs 2026 octant</option>
                <option value="bpm">Tempo (BPM)</option>
                <option value="loudness">Loudness (LUFS)</option>
                <optgroup label="Mood tag probability">
                  {meta.mood_tags.map((t) => (
                    <option key={t} value={`tag:${t}`}>
                      {t}
                    </option>
                  ))}
                </optgroup>
              </select>
            </label>
            <span className="spacer" />
            <button type="button" aria-pressed={mapOptions.domainMode === "fit"} onClick={() => mapOptions.setDomainMode("fit")}>
              Fit data
            </button>
            <button type="button" aria-pressed={mapOptions.domainMode === "full"} onClick={() => mapOptions.setDomainMode("full")}>
              Full circumplex
            </button>
            <button type="button" onClick={mapOptions.onResetZoom}>
              Reset zoom
            </button>
          </>
        )}
      </div>
      <div className="control-row chips" aria-label="Mood tags">
        {chips.map((t) => (
          <button
            key={t}
            type="button"
            aria-pressed={filters.tags.has(t)}
            onClick={() => setFilters({ ...filters, tags: toggle(filters.tags, t) })}
          >
            {t}
          </button>
        ))}
        {others.length > 0 && (
          <select
            aria-label="More mood tags"
            value=""
            onChange={(e) => e.target.value && setFilters({ ...filters, tags: toggle(filters.tags, e.target.value) })}
          >
            <option value="">More tags…</option>
            {others.map((t) => (
              <option key={t} value={t}>
                {filters.tags.has(t) ? `✓ ${t}` : t}
              </option>
            ))}
          </select>
        )}
      </div>
      <div className="control-row chips" aria-label="Octants">
        {meta.octants.map(({ name }) => (
          <button
            key={name}
            type="button"
            aria-pressed={filters.octants.has(name)}
            onClick={() => setFilters({ ...filters, octants: toggle(filters.octants, name) })}
          >
            {name}
          </button>
        ))}
        {dirty ? (
          <button type="button" onClick={() => setFilters(NO_FILTERS)}>
            Clear filters
          </button>
        ) : null}
      </div>
    </div>
  );
}

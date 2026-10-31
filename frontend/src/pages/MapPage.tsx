import { useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { agreement, sequential, SEQ_STEPS, type Agreement } from "../features/map/colors";
import { visibleMask } from "../features/map/filters";
import { MapControls } from "../features/map/MapControls";
import { MapLegend, type LegendSpec } from "../features/map/MapLegend";
import { MoodMapView, type PointColors } from "../features/map/MoodMapView";
import { SelectionPanel } from "../features/map/SelectionPanel";
import { useMapValues, useMeta, useMoodMap } from "../data/hooks";
import { useLibrary } from "../state/library";

const EVAL_URL =
  "https://github.com/circuitflow/moody/blob/main/eval/results/deam_orientation.md";

export function MapPage() {
  const meta = useMeta();
  const mapQuery = useMoodMap();
  const { filters, setFilters, colorBy, setColorBy, selection, setSelection } = useLibrary();
  const [domainMode, setDomainMode] = useState<"fit" | "full">("fit");
  const [resetKey, setResetKey] = useState(0);
  const navigate = useNavigate();
  const field = colorBy.kind === "field" ? colorBy.field : null;
  const values = useMapValues(field);
  const map = mapQuery.data;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setSelection(new Set());
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setSelection]);

  const visible = useMemo(() => (map ? visibleMask(map, filters) : []), [map, filters]);

  const { colors, legend } = useMemo((): { colors: PointColors; legend: LegendSpec } => {
    if (!map) return { colors: { kind: "single" }, legend: { kind: "none" } };
    if (colorBy.kind === "agreement") {
      const cats = map.octant.map((o, i) => agreement(o, map.octant_2007[i] ?? null));
      const counts: Record<Agreement, number> = { same: 0, adjacent: 0, different: 0, none: 0 };
      cats.forEach((c, i) => visible[i] && counts[c]++);
      return { colors: { kind: "categorical", categoryOf: (r) => cats[r]! }, legend: { kind: "categorical", counts } };
    }
    if (colorBy.kind === "field" && values.data && values.data.values.length === map.id.length) {
      const vals = values.data.values;
      const { colorOf, legend: seq } = sequential(vals, SEQ_STEPS);
      return {
        colors: { kind: "sequential", colorOf: (r) => colorOf(vals[r] ?? null) },
        legend: { kind: "sequential", field: colorBy.field, legend: seq, missing: vals.filter((v) => v === null).length },
      };
    }
    return { colors: { kind: "single" }, legend: { kind: "none" } };
  }, [map, colorBy, values.data, visible]);

  if (mapQuery.isError || meta.isError) return <p role="alert">Could not load the library.</p>;
  if (!map || !meta.data) return <p className="muted">Loading map…</p>;
  if (map.id.length === 0) {
    return (
      <p className="card">
        No analyzed tracks yet. Run <code>moody scan &lt;music folder&gt;</code>, then reload.
      </p>
    );
  }

  const shown = visible.filter(Boolean).length;
  return (
    <section aria-label="Mood map" className="map-page">
      <MapControls
        meta={meta.data}
        map={map}
        filters={filters}
        setFilters={setFilters}
        colorBy={colorBy}
        setColorBy={setColorBy}
        domainMode={domainMode}
        setDomainMode={setDomainMode}
        onResetZoom={() => setResetKey((k) => k + 1)}
      />
      <p className="count num" aria-live="polite">
        Showing {shown} of {map.id.length} tracks
      </p>
      <div className="map-layout">
        <div className="card map-card" style={{ opacity: values.isFetching ? 0.6 : 1 }}>
          <MoodMapView
            map={map}
            visible={visible}
            colors={colors}
            selection={selection}
            onSelect={setSelection}
            onOpen={(id) => navigate({ to: "/track/$trackId", params: { trackId: String(id) } })}
            domainMode={domainMode}
            resetKey={resetKey}
          />
          <MapLegend spec={legend} />
          <p className="note muted">
            Valence and arousal are estimates from a pretrained model. Its valence leans on loudness
            and aggression more than listeners do, so loud tracks can look happier than they are (
            <a href={EVAL_URL} target="_blank" rel="noreferrer">
              evaluation
            </a>
            ). Drag to pan, scroll to zoom, click a dot to open the track.
          </p>
        </div>
        <SelectionPanel map={map} selection={selection} onClear={() => setSelection(new Set())} />
      </div>
    </section>
  );
}

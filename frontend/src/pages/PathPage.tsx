/**
 * Mood-path playlists: drag a start and an end mood on the map (optionally a point to bend
 * through) and get an ordered playlist that walks between them. The planner runs in the browser,
 * so this page works the same in the static demo. The path lives in the URL, so it can be shared.
 */
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { useDeferredValue, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { MoodMap } from "../api/types";
import { useAudioUrlFor, useMeta, useMoodMap, useStyleVectors } from "../data/hooks";
import { visibleMask } from "../features/map/filters";
import { MapControls } from "../features/map/MapControls";
import { MoodMapView } from "../features/map/MoodMapView";
import {
  anchorName,
  formatPoint,
  LENGTH_RANGE,
  OCTANT_NAMES,
  PATH_DEFAULTS,
  resolvePoint,
  round,
  type PathSearch,
} from "../features/path/anchors";
import { PathOverlay, type HandleKey } from "../features/path/PathOverlay";
import { SavePlaylist } from "../features/path/SavePlaylist";
import { alignStyle, planPath, type PathRequest, type Point } from "../features/path/planner";
import { useLibrary } from "../state/library";

interface Props {
  search: PathSearch;
  setSearch: (next: PathSearch) => void;
}

const signed = (x: number) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(2);

/** The route component: the path lives in the URL, so a playlist can be shared as a link. */
export function PathRoute() {
  const search = useSearch({ from: "/path" });
  const navigate = useNavigate();
  return (
    <PathPage
      search={search}
      setSearch={(next) => navigate({ to: "/path", search: next, replace: true })}
    />
  );
}

export function PathPage({ search, setSearch }: Props) {
  const meta = useMeta();
  const mapQuery = useMoodMap();
  const style = useStyleVectors();
  const map = mapQuery.data;

  if (mapQuery.isError || meta.isError) return <p role="alert">Could not load the library.</p>;
  if (!map || !meta.data || style.isPending) return <p className="muted">Loading…</p>;
  if (map.id.length === 0) {
    return (
      <p className="card">
        No analyzed tracks yet. Run <code>moody scan &lt;music folder&gt;</code>, then reload.
      </p>
    );
  }
  return (
    <PathBuilder
      map={map}
      meta={meta.data}
      style={style.data ?? null}
      search={search}
      setSearch={setSearch}
    />
  );
}

function PathBuilder({
  map,
  meta,
  style,
  search,
  setSearch,
}: Props & {
  map: MoodMap;
  meta: NonNullable<ReturnType<typeof useMeta>["data"]>;
  style: ReturnType<typeof useStyleVectors>["data"] | null;
}) {
  const navigate = useNavigate();
  const audioUrlFor = useAudioUrlFor();
  const { filters, setFilters } = useLibrary();
  const [drag, setDrag] = useState<{ key: HandleKey; point: Point } | null>(null);

  const fromUrl = (spec: string | undefined, fallback: string) =>
    resolvePoint(spec, map) ?? resolvePoint(fallback, map)!;
  const start = drag?.key === "start" ? drag.point : fromUrl(search.from, PATH_DEFAULTS.from);
  const end = drag?.key === "end" ? drag.point : fromUrl(search.to, PATH_DEFAULTS.to);
  const via = drag?.key === "via" ? drag.point : resolvePoint(search.via, map);
  const length = search.n ?? PATH_DEFAULTS.n;
  const smoothness = search.s ?? PATH_DEFAULTS.s;

  const eligible = useMemo(() => visibleMask(map, filters), [map, filters]);
  const aligned = useMemo(() => (style ? alignStyle(map.id, style) : null), [map, style]);
  const library = useMemo(
    () => ({ valence: map.valence, arousal: map.arousal, artist: map.artist, style: aligned, eligible }),
    [map, aligned, eligible],
  );
  const request = useMemo<PathRequest>(
    () => ({ start, end, via, length, smoothness }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- points compared by value
    [start[0], start[1], end[0], end[1], via?.[0], via?.[1], length, smoothness],
  );
  // While a handle is dragged, the map stays responsive and the playlist catches up.
  const deferred = useDeferredValue(request);
  const plan = useMemo(() => planPath(library, deferred), [library, deferred]);
  const chosen = useMemo(() => new Set(plan.rows.map((r) => map.id[r]!)), [plan, map]);

  const update = (patch: Partial<PathSearch>) => {
    const next: PathSearch = { ...search, ...patch };
    for (const key of Object.keys(next) as (keyof PathSearch)[]) {
      if (next[key] === undefined) delete next[key];
    }
    setSearch(next);
  };
  const pointSpec = (p: Point) => anchorName(p, map) ?? formatPoint(p);
  const onMove = (key: HandleKey, point: Point, final: boolean) => {
    if (!final) return setDrag({ key, point });
    setDrag(null);
    update({ [key === "start" ? "from" : key === "end" ? "to" : "via"]: pointSpec(point) });
  };
  const toggleBend = (on: boolean) => {
    if (!on) return update({ via: undefined });
    // Start the bend a little off the middle of the line, toward the origin side.
    const mid: Point = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2];
    const [dx, dy] = [end[0] - start[0], end[1] - start[1]];
    const len = Math.hypot(dx, dy) || 1;
    const offset = 0.25 * len;
    update({ via: formatPoint([round(mid[0] - (dy / len) * offset), round(mid[1] + (dx / len) * offset)]) });
  };

  const handles = [
    { key: "start" as const, label: "Start", point: start },
    { key: "end" as const, label: "End", point: end },
    ...(via ? [{ key: "via" as const, label: "Via", point: via }] : []),
  ];
  const eligibleCount = eligible.filter(Boolean).length;
  const startName = anchorName(start, map);
  const endName = anchorName(end, map);

  return (
    <section aria-label="Mood path" className="map-page">
      <MapControls meta={meta} map={map} filters={filters} setFilters={setFilters} />
      <div className="map-layout path-layout">
        <div className="card map-card">
          <MoodMapView
            map={map}
            visible={eligible}
            colors={{ kind: "single" }}
            selection={chosen}
            onSelect={() => {}}
            onOpen={(id) => navigate({ to: "/track/$trackId", params: { trackId: String(id) } })}
            domainMode="fit"
            resetKey={0}
            lasso={false}
            overlay={(ctx) => (
              <PathOverlay
                ctx={ctx}
                waypoints={plan.waypoints}
                route={plan.rows.map((r) => [map.valence[r]!, map.arousal[r]!] as const)}
                handles={handles}
                onMove={onMove}
              />
            )}
          />
          <p className="note muted">
            Drag <strong>Start</strong> and <strong>End</strong> (or focus one and use the arrow keys).
            The dashed line is the mood path, and the numbered dots are the playlist in order.
          </p>
        </div>
        <PathPanel
          map={map}
          plan={plan}
          save={
            <SavePlaylist
              trackIds={plan.rows.map((r) => map.id[r]!)}
              start={start}
              end={end}
              via={via}
              defaultName={`${startName ?? "Custom point"} → ${endName ?? "Custom point"}`}
              params={{
                search,
                filters: { query: filters.query, tags: [...filters.tags], octants: [...filters.octants] },
              }}
            />
          }
          eligibleCount={eligibleCount}
          length={length}
          smoothness={smoothness}
          startName={startName}
          endName={endName}
          bend={via !== null}
          hasStyle={aligned !== null && aligned.dims > 0}
          audioUrl={audioUrlFor}
          onFrom={(name) => update({ from: name })}
          onTo={(name) => update({ to: name })}
          onSwap={() => update({ from: pointSpec(end), to: pointSpec(start) })}
          onBend={toggleBend}
          onLength={(n) => update({ n })}
          onSmoothness={(s) => update({ s })}
        />
      </div>
    </section>
  );
}

interface PanelProps {
  map: MoodMap;
  plan: ReturnType<typeof planPath>;
  save: ReactNode;
  eligibleCount: number;
  length: number;
  smoothness: number;
  startName: string | null;
  endName: string | null;
  bend: boolean;
  hasStyle: boolean;
  audioUrl: (id: number) => string | null;
  onFrom: (name: string) => void;
  onTo: (name: string) => void;
  onSwap: () => void;
  onBend: (on: boolean) => void;
  onLength: (n: number) => void;
  onSmoothness: (s: number) => void;
}

function PathPanel(p: PanelProps) {
  const { map, plan } = p;
  const audioRef = useRef<HTMLAudioElement>(null);
  // Playback belongs to one version of the playlist: a new plan stops it.
  const planKey = plan.rows.join(",");
  const [player, setPlayer] = useState<{ key: string; pos: number } | null>(null);
  const playing = player?.key === planKey ? player.pos : null;
  const playable = plan.rows.length > 0 && p.audioUrl(map.id[plan.rows[0]!]!) !== null;
  useEffect(() => audioRef.current?.pause(), [planKey]);

  const playAt = (pos: number | null) => {
    const audio = audioRef.current;
    if (pos === null || pos >= plan.rows.length) {
      audio?.pause();
      setPlayer(null);
      return;
    }
    setPlayer({ key: planKey, pos });
    if (!audio) return;
    audio.src = p.audioUrl(map.id[plan.rows[pos]!]!) ?? "";
    void audio.play?.()?.catch(() => setPlayer(null));
  };

  return (
    <aside className="card path-panel" aria-label="Playlist">
      <div className="path-ends">
        <label>
          From
          <select value={p.startName ?? ""} onChange={(e) => p.onFrom(e.target.value)}>
            {!p.startName && <option value="">Custom point</option>}
            {OCTANT_NAMES.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </label>
        <button type="button" onClick={p.onSwap} aria-label="Swap start and end" title="Swap start and end">
          ⇄
        </button>
        <label>
          To
          <select value={p.endName ?? ""} onChange={(e) => p.onTo(e.target.value)}>
            {!p.endName && <option value="">Custom point</option>}
            {OCTANT_NAMES.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </label>
      </div>
      <label className="path-check">
        <input type="checkbox" checked={p.bend} onChange={(e) => p.onBend(e.target.checked)} /> Bend through a
        point
      </label>
      <label className="path-slider">
        <span>
          Length <span className="num">{p.length}</span>
        </span>
        <input
          type="range"
          min={LENGTH_RANGE[0]}
          max={LENGTH_RANGE[1]}
          value={p.length}
          onChange={(e) => p.onLength(Number(e.target.value))}
        />
      </label>
      <label className="path-slider">
        <span>Smoothness</span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={p.smoothness}
          disabled={!p.hasStyle}
          onChange={(e) => p.onSmoothness(Number(e.target.value))}
          aria-valuetext={`${Math.round(p.smoothness * 100)}%`}
        />
        <span className="path-slider-ends muted">
          <span>Follow the mood</span>
          <span>Keep the sound</span>
        </span>
      </label>

      {plan.rows.length < p.length && (
        <p className="note muted">
          Only {p.eligibleCount} track{p.eligibleCount === 1 ? "" : "s"} match the filters, so the playlist has{" "}
          {plan.rows.length}.
        </p>
      )}
      {plan.relaxed && (
        <p className="note muted">Too few different artists here: some artists repeat within three tracks.</p>
      )}
      {!p.hasStyle && <p className="note muted">Sound similarity isn't available, so only mood is used.</p>}

      {p.save}

      {playable && (
        <div className="path-player">
          <button type="button" onClick={() => playAt(playing === null ? 0 : null)}>
            {playing === null ? "▶ Play all" : "■ Stop"}
          </button>
          <audio ref={audioRef} onEnded={() => playAt((playing ?? -1) + 1)} preload="none" />
        </div>
      )}

      <ol className="path-list">
        {plan.rows.map((row, i) => {
          const id = map.id[row]!;
          return (
            <li key={id} aria-current={playing === i ? "true" : undefined}>
              {playable ? (
                <button
                  type="button"
                  className="path-play"
                  onClick={() => playAt(playing === i ? null : i)}
                  aria-label={`${playing === i ? "Stop" : "Play"} ${map.title[row] ?? "Untitled"}`}
                >
                  {playing === i ? "■" : "▶"}
                </button>
              ) : (
                <span className="path-pos num">{i + 1}</span>
              )}
              <span className="path-track">
                <Link to="/track/$trackId" params={{ trackId: String(id) }}>
                  {map.title[row] ?? "Untitled"}
                </Link>
                <span className="secondary">{map.artist[row] ?? "Unknown artist"}</span>
              </span>
              <span className="num muted path-va" title="Valence, arousal">
                {signed(map.valence[row]!)} {signed(map.arousal[row]!)}
              </span>
            </li>
          );
        })}
      </ol>
    </aside>
  );
}

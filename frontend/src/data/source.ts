/**
 * The UI talks to a DataSource, never to fetch() directly, so the same components
 * serve both the self-hosted app (FastAPI) and the static GitHub Pages demo.
 * The static layout is written by `moody export-static` and mirrors the API one-to-one.
 */
import type {
  Embeddings,
  MapValues,
  Meta,
  MoodMap,
  Neighbor,
  PlaylistCreate,
  PlaylistDetail,
  PlaylistSummary,
  TrackDetail,
} from "../api/types";

export interface DataSource {
  readonly kind: "api" | "static";
  meta(): Promise<Meta>;
  map(): Promise<MoodMap>;
  mapValues(field: string): Promise<MapValues>;
  track(id: number): Promise<TrackDetail>;
  neighbors(id: number): Promise<Neighbor[]>;
  /** Compact style vectors for the path planner, aligned with `map().id`. */
  embeddings(): Promise<Embeddings>;
  /** A playable URL for the track's audio, or null when the source has none. */
  audioUrl(id: number): string | null;
  /** Saved playlists need the self-hosted app; the static demo shares paths as links instead. */
  readonly canSave: boolean;
  playlists(): Promise<PlaylistSummary[]>;
  playlist(id: number): Promise<PlaylistDetail>;
  savePlaylist(body: PlaylistCreate): Promise<PlaylistDetail>;
  deletePlaylist(id: number): Promise<void>;
  /** Download URL for the playlist as M3U8 (absolute local paths), or null. */
  m3uUrl(id: number): string | null;
}

const NOT_IN_DEMO = "Saved playlists need the self-hosted app.";

async function getJson<T>(url: string): Promise<T> {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`${url}: HTTP ${resp.status}`);
  return (await resp.json()) as T;
}

async function send(method: "POST" | "DELETE", url: string, body?: unknown): Promise<Response> {
  const resp = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const json = (await resp.json()) as { detail?: unknown };
      if (typeof json.detail === "string") detail = json.detail;
    } catch {
      // keep the status line
    }
    throw new Error(detail);
  }
  return resp;
}

export class ApiDataSource implements DataSource {
  readonly kind = "api";
  constructor(private readonly baseUrl = "") {}
  meta() {
    return getJson<Meta>(`${this.baseUrl}/api/meta`);
  }
  map() {
    return getJson<MoodMap>(`${this.baseUrl}/api/map`);
  }
  mapValues(field: string) {
    return getJson<MapValues>(`${this.baseUrl}/api/map/values?field=${encodeURIComponent(field)}`);
  }
  track(id: number) {
    return getJson<TrackDetail>(`${this.baseUrl}/api/tracks/${id}`);
  }
  neighbors(id: number) {
    return getJson<Neighbor[]>(`${this.baseUrl}/api/tracks/${id}/neighbors`);
  }
  embeddings() {
    return getJson<Embeddings>(`${this.baseUrl}/api/embeddings`);
  }
  audioUrl(id: number) {
    return `${this.baseUrl}/api/audio/${id}`;
  }
  readonly canSave = true;
  playlists() {
    return getJson<PlaylistSummary[]>(`${this.baseUrl}/api/playlists`);
  }
  playlist(id: number) {
    return getJson<PlaylistDetail>(`${this.baseUrl}/api/playlists/${id}`);
  }
  async savePlaylist(body: PlaylistCreate) {
    return (await (await send("POST", `${this.baseUrl}/api/playlists`, body)).json()) as PlaylistDetail;
  }
  async deletePlaylist(id: number) {
    await send("DELETE", `${this.baseUrl}/api/playlists/${id}`);
  }
  m3uUrl(id: number) {
    return `${this.baseUrl}/api/playlists/${id}/m3u`;
  }
}

export class StaticDataSource implements DataSource {
  readonly kind = "static";
  constructor(private readonly dataUrl = `${import.meta.env.BASE_URL}data`) {}
  meta() {
    return getJson<Meta>(`${this.dataUrl}/meta.json`);
  }
  map() {
    return getJson<MoodMap>(`${this.dataUrl}/map.json`);
  }
  mapValues(field: string) {
    return getJson<MapValues>(`${this.dataUrl}/map-values/${field.replace(":", "-")}.json`);
  }
  track(id: number) {
    return getJson<TrackDetail>(`${this.dataUrl}/tracks/${id}.json`);
  }
  neighbors(id: number) {
    return getJson<Neighbor[]>(`${this.dataUrl}/neighbors/${id}.json`);
  }
  embeddings() {
    return getJson<Embeddings>(`${this.dataUrl}/embeddings.json`);
  }
  audioUrl() {
    return null;
  }
  readonly canSave = false;
  async playlists() {
    return [];
  }
  playlist(): Promise<PlaylistDetail> {
    return Promise.reject(new Error(NOT_IN_DEMO));
  }
  savePlaylist(): Promise<PlaylistDetail> {
    return Promise.reject(new Error(NOT_IN_DEMO));
  }
  deletePlaylist(): Promise<void> {
    return Promise.reject(new Error(NOT_IN_DEMO));
  }
  m3uUrl() {
    return null;
  }
}

export function createDataSource(): DataSource {
  return import.meta.env.VITE_DATA_SOURCE === "static"
    ? new StaticDataSource()
    : new ApiDataSource();
}

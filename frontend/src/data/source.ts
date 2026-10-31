/**
 * The UI talks to a DataSource, never to fetch() directly, so the same components
 * serve both the self-hosted app (FastAPI) and the static GitHub Pages demo.
 * The static layout is written by `moody export-static` and mirrors the API one-to-one.
 */
import type { MapValues, Meta, MoodMap, Neighbor, TrackDetail } from "../api/types";

export interface DataSource {
  readonly kind: "api" | "static";
  meta(): Promise<Meta>;
  map(): Promise<MoodMap>;
  mapValues(field: string): Promise<MapValues>;
  track(id: number): Promise<TrackDetail>;
  neighbors(id: number): Promise<Neighbor[]>;
  /** A playable URL for the track's audio, or null when the source has none. */
  audioUrl(id: number): string | null;
}

async function getJson<T>(url: string): Promise<T> {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`${url}: HTTP ${resp.status}`);
  return (await resp.json()) as T;
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
  audioUrl(id: number) {
    return `${this.baseUrl}/api/audio/${id}`;
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
  audioUrl() {
    return null;
  }
}

export function createDataSource(): DataSource {
  return import.meta.env.VITE_DATA_SOURCE === "static"
    ? new StaticDataSource()
    : new ApiDataSource();
}

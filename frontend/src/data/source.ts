/**
 * The UI talks to a DataSource, never to fetch() directly, so the same components
 * serve both the self-hosted app (FastAPI) and the static GitHub Pages demo.
 */
export interface Health {
  status: string;
  version: string;
}

export interface DataSource {
  readonly kind: "api" | "static";
  health(): Promise<Health>;
}

async function getJson<T>(url: string): Promise<T> {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`${url}: HTTP ${resp.status}`);
  return (await resp.json()) as T;
}

export class ApiDataSource implements DataSource {
  readonly kind = "api";
  constructor(private readonly baseUrl = "") {}
  health(): Promise<Health> {
    return getJson<Health>(`${this.baseUrl}/api/health`);
  }
}

export class StaticDataSource implements DataSource {
  readonly kind = "static";
  constructor(private readonly dataUrl = `${import.meta.env.BASE_URL}data`) {}
  health(): Promise<Health> {
    return getJson<Health>(`${this.dataUrl}/meta.json`);
  }
}

export function createDataSource(): DataSource {
  return import.meta.env.VITE_DATA_SOURCE === "static"
    ? new StaticDataSource()
    : new ApiDataSource();
}

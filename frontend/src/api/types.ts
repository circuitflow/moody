/** Friendly names for the generated API types (src/api/schema.d.ts, from openapi.json). */
import type { components } from "./schema";

type S = components["schemas"];
export type Meta = S["Meta"];
export type MoodMap = S["MoodMap"];
export type MapValues = S["MapValues"];
export type TrackDetail = S["TrackDetail"];
export type TrackSummary = S["TrackSummary"];
export type Neighbor = S["Neighbor"];
export type Segment = S["SegmentOut"];
export type Embeddings = S["Embeddings"];
export type PlaylistCreate = S["PlaylistCreate"];
export type PlaylistSummary = S["PlaylistSummary"];
export type PlaylistDetail = S["PlaylistDetail"];
export type SpotifyStatus = S["SpotifyStatus"];
export type SpotifyExport = S["SpotifyExport"];
export type HistorySummary = S["HistorySummary"];
export type HistoryImport = S["HistoryImport"];
export type HistoryMood = S["HistoryMood"];
export type MoodBucket = S["MoodBucket"];
export type TopTrack = S["TopTrack"];
export type Attribution = S["Attribution"];
/** One line of the demo's credits.json (written by `moody export-static --demo`). */
export interface Credit extends Attribution {
  id: number;
  audio_url?: string | null;
}
export type Job = S["JobOut"];

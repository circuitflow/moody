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

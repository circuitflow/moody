/** A small deterministic in-memory library for component tests. */
import type { Embeddings, MapValues, Meta, MoodMap, Neighbor, TrackDetail } from "../api/types";
import { encodeEmbeddings } from "../features/path/embeddings";
import type { DataSource } from "../data/source";

const OCTANTS = [
  "Pleasure", "Excitement", "Arousal", "Distress",
  "Displeasure", "Depression", "Sleepiness", "Relaxation",
];

export interface FakeTrack {
  id: number;
  title: string;
  artist: string;
  valence: number;
  arousal: number;
  tags: string[];
  bpm: number;
  octant2007: string;
}

export const FAKE_TRACKS: FakeTrack[] = [
  { id: 1, title: "Happy Song", artist: "Band A", valence: 0.5, arousal: 0.4, tags: ["happy", "energetic"], bpm: 128, octant2007: "Excitement" },
  { id: 2, title: "Sad Song", artist: "Band B", valence: -0.3, arousal: -0.35, tags: ["sad", "melancholic"], bpm: 70, octant2007: "Depression" },
  { id: 3, title: "Calm Song", artist: "Band A", valence: 0.3, arousal: -0.4, tags: ["calm", "relaxing"], bpm: 80, octant2007: "Pleasure" },
  { id: 4, title: "Angry Song", artist: "Band C", valence: -0.4, arousal: 0.45, tags: ["dark", "heavy"], bpm: 160, octant2007: "Relaxation" },
];

function octantOf(v: number, a: number): string {
  const angle = ((Math.atan2(a, v) * 180) / Math.PI + 360) % 360;
  return OCTANTS[Math.round(angle / 45) % 8]!;
}

export function fakeDetail(t: FakeTrack): TrackDetail {
  return {
    id: t.id, title: t.title, artist: t.artist, album: "Album", duration_s: 200, status: "analyzed",
    valence: t.valence, arousal: t.arousal, octant: octantOf(t.valence, t.arousal), top_tags: t.tags,
    bpm: t.bpm, key: "C", scale: "major", loudness_lufs: -10,
    mood_probs: { happy: 0.6, sad: 0.2, aggressive: 0.1, relaxed: 0.4, party: 0.3 },
    tag_probs: Object.fromEntries(t.tags.map((tag, i) => [tag, 0.5 - i * 0.1])),
    segments: [0, 1, 2, 3].map((i) => ({
      start_s: i * 1.5, valence: t.valence + i * 0.02, arousal: t.arousal - i * 0.02,
    })),
    thesis_2007: {
      octant: t.octant2007, hevner: "cheerful",
      features: { mode: 60, harmony: 80, tempo: 55, rhythm: 70, loudness: 52 },
    },
    pipeline_version: "test", error: null,
    duplicate_of: null,
    alternates: t.id === 1 ? [{ id: 99, format: "MP3" }] : [],
  };
}

export class FakeSource implements DataSource {
  readonly kind = "api" as const;
  constructor(private readonly tracks: FakeTrack[] = FAKE_TRACKS) {}
  async meta(): Promise<Meta> {
    return {
      version: "test", pipeline_version: "p1", tracks: this.tracks.length, analyzed: this.tracks.length,
      duplicates: 1,
      mood_tags: ["calm", "dark", "energetic", "happy", "heavy", "melancholic", "relaxing", "sad"],
      octants: OCTANTS.map((name, i) => ({ name, angle_deg: i * 45 })),
      map_fields: ["bpm", "loudness", "tag:happy"], audio: true,
    };
  }
  async map(): Promise<MoodMap> {
    const t = this.tracks;
    return {
      id: t.map((x) => x.id), valence: t.map((x) => x.valence), arousal: t.map((x) => x.arousal),
      octant: t.map((x) => octantOf(x.valence, x.arousal)), tag: t.map((x) => x.tags[0] ?? null),
      tags: t.map((x) => x.tags.join(" ")), octant_2007: t.map((x) => x.octant2007), title: t.map((x) => x.title), artist: t.map((x) => x.artist),
    };
  }
  async mapValues(field: string): Promise<MapValues> {
    return { field, values: this.tracks.map((x) => (field === "bpm" ? x.bpm : 0.5)) };
  }
  async track(id: number): Promise<TrackDetail> {
    const t = this.tracks.find((x) => x.id === id);
    if (!t) throw new Error("not found");
    return fakeDetail(t);
  }
  async neighbors(id: number): Promise<Neighbor[]> {
    return this.tracks
      .filter((x) => x.id !== id)
      .map((x, i) => ({
        id: x.id, title: x.title, artist: x.artist, similarity: 0.9 - i * 0.1,
        valence: x.valence, arousal: x.arousal, octant: octantOf(x.valence, x.arousal),
      }));
  }
  async embeddings(): Promise<Embeddings> {
    // A unit vector per track, at an angle set by its id: nearby ids sound alike.
    return encodeEmbeddings(
      this.tracks.map((x) => x.id),
      this.tracks.map((x) => [Math.cos(x.id * 0.7), Math.sin(x.id * 0.7)]),
    );
  }
  audioUrl(id: number): string | null {
    return `/api/audio/${id}`;
  }
}

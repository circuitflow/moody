import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import type { PlaylistCreate } from "../api/types";
import type { Period } from "./source";
import { decodeEmbeddings } from "../features/path/embeddings";
import { useDataSource } from "./context";

export function useMeta() {
  const source = useDataSource();
  return useQuery({ queryKey: ["meta"], queryFn: () => source.meta(), staleTime: Infinity });
}

export function useMoodMap() {
  const source = useDataSource();
  return useQuery({ queryKey: ["map"], queryFn: () => source.map(), staleTime: Infinity });
}

export function useMapValues(field: string | null) {
  const source = useDataSource();
  return useQuery({
    queryKey: ["map-values", field],
    queryFn: () => source.mapValues(field!),
    enabled: field !== null,
    staleTime: Infinity,
    placeholderData: (previous) => previous, // keep the old colors while the new field loads
  });
}

export function useTrack(id: number) {
  const source = useDataSource();
  return useQuery({ queryKey: ["track", id], queryFn: () => source.track(id), staleTime: Infinity });
}

export function useNeighbors(id: number) {
  const source = useDataSource();
  return useQuery({
    queryKey: ["neighbors", id],
    queryFn: () => source.neighbors(id),
    staleTime: Infinity,
  });
}

/** Style vectors for the path planner, decoded once. */
export function useStyleVectors() {
  const source = useDataSource();
  return useQuery({
    queryKey: ["embeddings"],
    queryFn: async () => decodeEmbeddings(await source.embeddings()),
    staleTime: Infinity,
  });
}

export function usePlaylists() {
  const source = useDataSource();
  return useQuery({ queryKey: ["playlists"], queryFn: () => source.playlists() });
}

export function usePlaylist(id: number) {
  const source = useDataSource();
  return useQuery({ queryKey: ["playlist", id], queryFn: () => source.playlist(id) });
}

export function useSavePlaylist() {
  const source = useDataSource();
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: PlaylistCreate) => source.savePlaylist(body),
    onSuccess: (saved) => {
      client.setQueryData(["playlist", saved.id], saved);
      void client.invalidateQueries({ queryKey: ["playlists"] });
    },
  });
}

export function useDeletePlaylist() {
  const source = useDataSource();
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => source.deletePlaylist(id),
    onSuccess: (_, id) => {
      client.removeQueries({ queryKey: ["playlist", id] });
      void client.invalidateQueries({ queryKey: ["playlists"] });
    },
  });
}

export function useSpotifyStatus() {
  const source = useDataSource();
  return useQuery({ queryKey: ["spotify"], queryFn: () => source.spotifyStatus(), enabled: source.canSave });
}

export function useSpotifyDisconnect() {
  const source = useDataSource();
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => source.spotifyDisconnect(),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["spotify"] }),
  });
}

export function useSpotifyExport() {
  const source = useDataSource();
  const client = useQueryClient();
  return useMutation({
    mutationFn: (playlistId: number) => source.exportToSpotify(playlistId),
    // A rejected sign-in disconnects on the server; refresh the status either way.
    onSettled: () => void client.invalidateQueries({ queryKey: ["spotify"] }),
  });
}

export function useHistorySummary() {
  const source = useDataSource();
  return useQuery({ queryKey: ["history"], queryFn: () => source.historySummary(), enabled: source.canSave });
}

export function useHistoryMood(bucket: "week" | "hour", tz: string, period: Period) {
  const source = useDataSource();
  return useQuery({
    queryKey: ["history", "mood", bucket, tz, period],
    queryFn: () => source.historyMood(bucket, tz, period),
    enabled: source.canSave,
    placeholderData: (previous) => previous,
  });
}

export function useHistoryTop(period: Period) {
  const source = useDataSource();
  return useQuery({
    queryKey: ["history", "top", period],
    queryFn: () => source.historyTop(period),
    enabled: source.canSave,
    placeholderData: (previous) => previous,
  });
}

export function useCredits() {
  const source = useDataSource();
  return useQuery({ queryKey: ["credits"], queryFn: () => source.credits(), staleTime: Infinity });
}

/** Where to play a track from: the self-hosted file, or (demo) its Jamendo stream. */
export function useAudioUrlFor(): (id: number) => string | null {
  const source = useDataSource();
  const credits = useCredits();
  return useMemo(() => {
    const streams = new Map((credits.data ?? []).map((c) => [c.id, c.audio_url ?? null]));
    return (id: number) => source.audioUrl(id) ?? streams.get(id) ?? null;
  }, [source, credits.data]);
}

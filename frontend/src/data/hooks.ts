import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { PlaylistCreate } from "../api/types";
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

import { useQuery } from "@tanstack/react-query";
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

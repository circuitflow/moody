import type { MoodMap } from "../../api/types";
import type { Filters } from "../../state/filters";

/** Which map rows pass the filters. Tag filters match any selected tag (OR); octants likewise. */
export function visibleMask(map: MoodMap, filters: Filters): boolean[] {
  const query = filters.query.trim().toLowerCase();
  return map.id.map((_, i) => {
    if (query) {
      const hay = `${map.title[i] ?? ""} ${map.artist[i] ?? ""}`.toLowerCase();
      if (!hay.includes(query)) return false;
    }
    if (filters.tags.size > 0) {
      const tags = (map.tags[i] ?? "").split(" ");
      if (!tags.some((t) => filters.tags.has(t))) return false;
    }
    if (filters.octants.size > 0 && !filters.octants.has(map.octant[i] ?? "")) return false;
    return true;
  });
}

/** Mood tags present in the library, most frequent first (for the filter chips). */
export function tagFrequencies(map: MoodMap): [string, number][] {
  const counts = new Map<string, number>();
  for (const tags of map.tags) {
    for (const t of tags.split(" ")) if (t) counts.set(t, (counts.get(t) ?? 0) + 1);
  }
  return [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

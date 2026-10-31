import { useParams } from "@tanstack/react-router";

export function TrackPage() {
  const { trackId } = useParams({ from: "/track/$trackId" });
  return <section aria-label="Track">Track {trackId}</section>;
}

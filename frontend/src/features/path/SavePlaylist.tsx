/** Save the current path as a playlist (self-hosted) or copy a link to it (anywhere). */
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useDataSource } from "../../data/context";
import { useSavePlaylist } from "../../data/hooks";
import type { Point } from "./planner";

interface Props {
  trackIds: number[];
  start: Point;
  end: Point;
  via: Point | null;
  defaultName: string;
  params: Record<string, unknown>;
}

export function SavePlaylist({ trackIds, start, end, via, defaultName, params }: Props) {
  const source = useDataSource();
  const save = useSavePlaylist();
  const [name, setName] = useState("");
  const [copied, setCopied] = useState(false);
  // A save result only counts for the playlist as it was saved.
  const saved = save.data && save.data.tracks.map((t) => t.id).join() === trackIds.join() ? save.data : null;

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="path-save">
      {source.canSave && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate({
              name: name.trim() || defaultName,
              track_ids: trackIds,
              start: [start[0], start[1]],
              end: [end[0], end[1]],
              via: via ? [via[0], via[1]] : null,
              params,
            });
          }}
        >
          <input
            aria-label="Playlist name"
            placeholder={defaultName}
            value={name}
            maxLength={200}
            onChange={(e) => setName(e.target.value)}
          />
          <button type="submit" disabled={trackIds.length === 0 || save.isPending}>
            {save.isPending ? "Saving…" : "Save"}
          </button>
        </form>
      )}
      <button type="button" onClick={copyLink}>
        {copied ? "Link copied" : "Copy link"}
      </button>
      {saved && (
        <p className="note" role="status">
          Saved as “{saved.name}”.{" "}
          <Link to="/playlists/$playlistId" params={{ playlistId: String(saved.id) }}>
            Open playlist
          </Link>
        </p>
      )}
      {save.isError && (
        <p className="note" role="alert">
          Could not save: {save.error.message}
        </p>
      )}
    </div>
  );
}

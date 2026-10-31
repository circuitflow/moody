/** Saved playlists (self-hosted): the list, and one playlist with its M3U download. */
import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { useState } from "react";
import type { PlaylistDetail } from "../api/types";
import { useDataSource } from "../data/context";
import { useDeletePlaylist, usePlaylist, usePlaylists } from "../data/hooks";
import { parsePathSearch } from "../features/path/anchors";
import { useLibrary } from "../state/library";

const signed = (x: number | null | undefined) =>
  x == null ? "–" : (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(2);
const date = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });

export function PlaylistsPage() {
  const source = useDataSource();
  const list = usePlaylists();
  if (!source.canSave) {
    return (
      <p className="card">
        Saved playlists need the self-hosted app. In the demo, build a <Link to="/path">mood path</Link> and
        share it with “Copy link”.
      </p>
    );
  }
  if (list.isError) return <p role="alert">Could not load playlists.</p>;
  if (!list.data) return <p className="muted">Loading…</p>;
  return (
    <section aria-label="Playlists" className="card playlists">
      <div className="playlists-head">
        <h2>Playlists</h2>
        <Link to="/path">New mood path</Link>
      </div>
      {list.data.length === 0 ? (
        <p className="muted">
          No saved playlists yet. Build one on the <Link to="/path">Path</Link> page and press Save.
        </p>
      ) : (
        <ul className="playlist-list">
          {list.data.map((p) => (
            <li key={p.id}>
              <Link to="/playlists/$playlistId" params={{ playlistId: String(p.id) }}>
                {p.name}
              </Link>
              <span className="muted num">
                {p.count} track{p.count === 1 ? "" : "s"} · {date(p.created_at)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function PlaylistPage() {
  const { playlistId } = useParams({ from: "/playlists/$playlistId" });
  const id = Number(playlistId);
  const playlist = usePlaylist(id);
  if (playlist.isError) {
    return (
      <p role="alert">
        Playlist not found. <Link to="/playlists">All playlists</Link>
      </p>
    );
  }
  if (!playlist.data) return <p className="muted">Loading…</p>;
  return <PlaylistView playlist={playlist.data} />;
}

function PlaylistView({ playlist }: { playlist: PlaylistDetail }) {
  const source = useDataSource();
  const navigate = useNavigate();
  const { setFilters } = useLibrary();
  const remove = useDeletePlaylist();
  const [confirming, setConfirming] = useState(false);
  const m3u = source.m3uUrl(playlist.id);
  const search = parsePathSearch((playlist.params.search ?? {}) as Record<string, unknown>);
  const filters = playlist.params.filters as { query?: string; tags?: string[]; octants?: string[] } | undefined;

  const reopen = () => {
    setFilters({
      query: filters?.query ?? "",
      tags: new Set(filters?.tags ?? []),
      octants: new Set(filters?.octants ?? []),
    });
    void navigate({ to: "/path", search });
  };

  return (
    <section aria-label={`Playlist ${playlist.name}`} className="card playlist">
      <p className="muted">
        <Link to="/playlists">Playlists</Link>
      </p>
      <h2>{playlist.name}</h2>
      <p className="muted num">
        {playlist.count} track{playlist.count === 1 ? "" : "s"} · saved {date(playlist.created_at)} · from (
        {signed(playlist.start[0])}, {signed(playlist.start[1])}) to ({signed(playlist.end[0])},{" "}
        {signed(playlist.end[1])})
      </p>
      <div className="playlist-actions">
        {m3u && (
          <a className="button" href={m3u} download>
            Download M3U
          </a>
        )}
        <button type="button" onClick={reopen}>
          Open in path builder
        </button>
        {confirming ? (
          <>
            <button
              type="button"
              onClick={() =>
                remove.mutate(playlist.id, { onSuccess: () => void navigate({ to: "/playlists" }) })
              }
              disabled={remove.isPending}
            >
              Confirm delete
            </button>
            <button type="button" onClick={() => setConfirming(false)}>
              Cancel
            </button>
          </>
        ) : (
          <button type="button" onClick={() => setConfirming(true)}>
            Delete
          </button>
        )}
      </div>
      {m3u && (
        <p className="note muted">
          The M3U file lists the tracks' paths on this computer. In Apple Music choose File → Library → Import
          Playlist; VLC and most players open it directly.
        </p>
      )}
      <ol className="path-list playlist-tracks">
        {playlist.tracks.map((t, i) => (
          <li key={t.id}>
            <span className="path-pos num">{i + 1}</span>
            <span className="path-track">
              <Link to="/track/$trackId" params={{ trackId: String(t.id) }}>
                {t.title ?? "Untitled"}
              </Link>
              <span className="secondary">{t.artist ?? "Unknown artist"}</span>
            </span>
            <span className="num muted path-va">
              {signed(t.valence)} {signed(t.arousal)}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

/** Connect Spotify and export a saved playlist to it (self-hosted). */
import { useDataSource } from "../../data/context";
import { useSpotifyDisconnect, useSpotifyExport, useSpotifyStatus } from "../../data/hooks";

export function SpotifyExport({ playlistId }: { playlistId: number }) {
  const source = useDataSource();
  const status = useSpotifyStatus();
  const exporter = useSpotifyExport();
  const disconnect = useSpotifyDisconnect();
  if (!source.canSave || !status.data) return null;
  const s = status.data;

  if (!s.configured) {
    return (
      <p className="note muted spotify">
        To export to Spotify, create an app at developer.spotify.com and set <code>MOODY_SPOTIFY_CLIENT_ID</code>{" "}
        (see the README).
      </p>
    );
  }

  const result = exporter.data;
  return (
    <div className="spotify" aria-label="Spotify">
      {s.error && (
        <p className="note" role="alert">
          {s.error}
        </p>
      )}
      {s.connected ? (
        <>
          <div className="spotify-row">
            <button type="button" onClick={() => exporter.mutate(playlistId)} disabled={exporter.isPending}>
              {exporter.isPending ? "Exporting…" : "Export to Spotify"}
            </button>
            <span className="muted">
              Connected as {s.account ?? "Spotify user"} ·{" "}
              <button type="button" className="link" onClick={() => disconnect.mutate()}>
                Disconnect
              </button>
            </span>
          </div>
          {exporter.isError && (
            <p className="note" role="alert">
              Export failed: {exporter.error.message}
            </p>
          )}
          {result && (
            <div className="note" role="status">
              <p>
                Created “{result.name}” on Spotify with {result.matched} of {result.total} tracks.{" "}
                {result.url && (
                  <a href={result.url} target="_blank" rel="noreferrer">
                    Open in Spotify ↗
                  </a>
                )}
              </p>
              {result.unmatched.length > 0 && (
                <details>
                  <summary>
                    {result.unmatched.length} not found on Spotify
                  </summary>
                  <ul>
                    {result.unmatched.map((t) => (
                      <li key={t.id}>
                        {t.title ?? "Untitled"} <span className="muted">— {t.artist ?? "Unknown artist"}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}
        </>
      ) : (
        <div className="spotify-row">
          <a className="button" href={source.spotifyLoginUrl(window.location.href) ?? "#"}>
            Connect Spotify
          </a>
          <span className="muted">to export this playlist to your account.</span>
        </div>
      )}
    </div>
  );
}

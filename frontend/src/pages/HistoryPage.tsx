/** Listening history (self-hosted): imports, coverage, and the mood of what you played. */
import { Link } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type { HistoryImport } from "../api/types";
import { useDataSource } from "../data/context";
import { useHistoryMood, useHistorySummary, useHistoryTop } from "../data/hooks";
import type { Period } from "../data/source";
import { MoodLines } from "../features/history/MoodLines";

const EVAL_URL = "https://github.com/circuitflow/moody/blob/main/eval/results/deam_orientation.md";
const PERIODS: [Period, string][] = [
  ["all", "All time"],
  ["year", "Last 12 months"],
  ["quarter", "Last 3 months"],
];
const SOURCE_NAMES: Record<string, string> = {
  lastfm: "Last.fm",
  spotify: "Spotify (recent)",
  "spotify-export": "Spotify (download)",
};

const fmt = (n: number) => n.toLocaleString();
const pct = (a: number, b: number) => (b ? `${Math.round((100 * a) / b)}%` : "–");
const day = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : "–";
const signed = (x: number | null | undefined) => (x == null ? "–" : (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(2));

const weekDate = (key: string) => new Date(`${key}T12:00:00`);
/** "Apr 27" on the axis, with the year on the first tick and in January. */
function weekTick(key: string, first: boolean) {
  const d = weekDate(key);
  const withYear = first || d.getMonth() === 0;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", ...(withYear ? { year: "numeric" } : {}) });
}
function weekLabel(key: string) {
  const d = weekDate(key).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  return `Week of ${d}`;
}
const hourTick = (key: string) => `${key.padStart(2, "0")}:00`;
const hourLabel = (key: string) => `${hourTick(key)}–${String((Number(key) + 1) % 24).padStart(2, "0")}:00`;
/** About six evenly spaced indices, always including the ends. */
function spread(n: number, count = 6): number[] {
  if (n <= 1) return n ? [0] : [];
  const step = Math.max(1, Math.round((n - 1) / (count - 1)));
  const out = [];
  for (let i = 0; i < n; i += step) out.push(i);
  if (out[out.length - 1] !== n - 1) out[out.length - 1] = n - 1;
  return out;
}

export function HistoryPage() {
  const source = useDataSource();
  const summary = useHistorySummary();
  const [period, setPeriod] = useState<Period>("all");
  const tz = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC", []);
  const weeks = useHistoryMood("week", tz, period);
  const hours = useHistoryMood("hour", tz, period);
  const top = useHistoryTop(period);

  if (!source.canSave) {
    return (
      <p className="card">
        Listening history needs the self-hosted app: it joins your Last.fm or Spotify plays to the music on your
        computer.
      </p>
    );
  }
  if (summary.isError) return <p role="alert">Could not load your listening history.</p>;
  if (!summary.data) return <p className="muted">Loading…</p>;
  const s = summary.data;

  return (
    <section aria-label="Listening history" className="history-page">
      <div className="card">
        <h2>Listening history</h2>
        <div className="stat-row">
          <div className="stat">
            <span className="stat-label">Plays imported</span>
            <span className="stat-value num">{fmt(s.plays)}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Matched to your library</span>
            <span className="stat-value num">
              {fmt(s.matched)} <span className="stat-unit">{pct(s.matched, s.plays)}</span>
            </span>
          </div>
          {s.sources.map((src) => (
            <div className="stat" key={src.source}>
              <span className="stat-label">{SOURCE_NAMES[src.source] ?? src.source}</span>
              <span className="stat-value num">{fmt(src.plays)}</span>
              <span className="muted stat-note">
                {day(src.first)} – {day(src.last)}
              </span>
            </div>
          ))}
        </div>
        <Importers lastfmConfigured={s.lastfm_configured} lastfmUser={s.lastfm_user} spotifyConnected={s.spotify_connected} />
        <p className="note muted">
          Only plays of songs Moody has analyzed have a mood. Scan more of your music to match more, then run{" "}
          <code>moody history status</code>. For your full Spotify history, request “Extended streaming history” in
          your Spotify account's privacy settings and run <code>moody history spotify-export &lt;zip&gt;</code>.
        </p>
      </div>

      {s.plays > 0 && (
        <>
          <div className="chips" role="group" aria-label="Period">
            {PERIODS.map(([value, name]) => (
              <button key={value} type="button" aria-pressed={period === value} onClick={() => setPeriod(value)}>
                {name}
              </button>
            ))}
          </div>
          <div className="card">
            <h3>Mood by week</h3>
            {weeks.data && weeks.data.points.some((p) => p.matched > 0) ? (
              <MoodLines
                title="Mood by week"
                points={weeks.data.points}
                tickLabel={weekTick}
                label={weekLabel}
                ticks={spread(weeks.data.points.length)}
              />
            ) : (
              <p className="muted">No matched plays in this period.</p>
            )}
            <p className="note muted">
              Each matched play counts once, so songs you play often weigh more. The model's valence leans on
              loudness (
              <a href={EVAL_URL} target="_blank" rel="noreferrer">
                evaluation
              </a>
              ), so compare weeks with each other rather than reading the values as absolute.
            </p>
          </div>
          <div className="card">
            <h3>Mood by hour of day</h3>
            {hours.data && hours.data.points.some((p) => p.matched > 0) ? (
              <MoodLines
                title="Mood by hour of day"
                points={hours.data.points}
                tickLabel={hourTick}
                label={hourLabel}
                ticks={[0, 3, 6, 9, 12, 15, 18, 21, 23]}
              />
            ) : (
              <p className="muted">No matched plays in this period.</p>
            )}
            <p className="note muted">Hours are in your time zone ({tz}).</p>
          </div>
          <div className="card">
            <h3>Most played</h3>
            {top.data && top.data.length > 0 ? (
              <ol className="path-list top-tracks">
                {top.data.map((t, i) => (
                  <li key={t.id}>
                    <span className="path-pos num">{i + 1}</span>
                    <span className="path-track">
                      <Link to="/track/$trackId" params={{ trackId: String(t.id) }}>
                        {t.title ?? "Untitled"}
                      </Link>
                      <span className="secondary">{t.artist ?? "Unknown artist"}</span>
                    </span>
                    <span className="num muted path-va">
                      {fmt(t.plays)} plays · {signed(t.valence)} {signed(t.arousal)}
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="muted">No matched plays in this period.</p>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function Importers({
  lastfmConfigured,
  lastfmUser,
  spotifyConnected,
}: {
  lastfmConfigured: boolean;
  lastfmUser: string | null;
  spotifyConnected: boolean;
}) {
  const source = useDataSource();
  const client = useQueryClient();
  const [user, setUser] = useState("");
  const [busy, setBusy] = useState<"lastfm" | "spotify" | null>(null);
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);

  const done = (r: HistoryImport, total: number) =>
    `${fmt(total)} new plays (${fmt(r.duplicates)} already imported). ${fmt(r.matched)} of ${fmt(r.plays)} plays ` +
    `now match your library (${pct(r.matched, r.plays)}).`;

  const run = async (kind: "lastfm" | "spotify") => {
    setBusy(kind);
    setMessage(null);
    try {
      let total = 0;
      let r: HistoryImport;
      if (kind === "spotify") {
        r = await source.importSpotifyRecent();
        total = r.new;
      } else {
        // Each call imports up to 2,000 scrobbles, oldest first; keep going while there's more.
        do {
          r = await source.importLastfm(user.trim() || undefined);
          total += r.new;
          if (r.more) setMessage({ text: `Imported ${fmt(total)} plays so far…` });
        } while (r.more);
      }
      setMessage({ text: done(r, total) });
    } catch (e) {
      setMessage({ text: (e as Error).message, error: true });
    } finally {
      setBusy(null);
      void client.invalidateQueries({ queryKey: ["history"] });
    }
  };

  return (
    <div className="importers">
      {lastfmConfigured ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run("lastfm");
          }}
        >
          <input
            aria-label="Last.fm user"
            placeholder={lastfmUser ?? "Last.fm user"}
            value={user}
            onChange={(e) => setUser(e.target.value)}
          />
          <button type="submit" disabled={busy !== null || (!user.trim() && !lastfmUser)}>
            {busy === "lastfm" ? "Importing…" : "Import from Last.fm"}
          </button>
        </form>
      ) : (
        <span className="muted">
          Last.fm: set <code>MOODY_LASTFM_API_KEY</code> to import scrobbles.
        </span>
      )}
      {spotifyConnected ? (
        <button type="button" onClick={() => void run("spotify")} disabled={busy !== null}>
          {busy === "spotify" ? "Syncing…" : "Sync recent Spotify plays"}
        </button>
      ) : (
        <span className="muted">
          Spotify: connect it from a <Link to="/playlists">playlist</Link> to sync recent plays.
        </span>
      )}
      {message && (
        <p className="note" role={message.error ? "alert" : "status"}>
          {message.text}
        </p>
      )}
    </div>
  );
}

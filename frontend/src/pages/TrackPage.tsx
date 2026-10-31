import { Link, useParams } from "@tanstack/react-router";
import { useRef, useState } from "react";
import { useDataSource } from "../data/context";
import { useMeta, useNeighbors, useTrack } from "../data/hooks";
import { Bars } from "../features/track/Bars";
import { clock, segmentAt, signed } from "../features/track/format";
import { MiniCircumplex } from "../features/track/MiniCircumplex";
import { ThesisCard } from "../features/track/ThesisCard";
import { TrajectoryChart } from "../features/track/TrajectoryChart";

const TOP_TAGS = 8;

export function TrackPage() {
  const { trackId } = useParams({ from: "/track/$trackId" });
  const id = Number(trackId);
  const track = useTrack(id);
  const near = useNeighbors(id);
  const meta = useMeta();
  const source = useDataSource();
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playhead, setPlayhead] = useState<number | null>(null);
  const [audioError, setAudioError] = useState(false);

  if (track.isError) {
    return (
      <section aria-label="Track" className="card">
        <p role="alert">Track not found.</p>
        <Link to="/">← Back to the map</Link>
      </section>
    );
  }
  if (!track.data) return <p className="muted">Loading track…</p>;
  const t = track.data;
  const audioUrl = source.audioUrl(id);
  const moodTags = new Set(meta.data?.mood_tags ?? Object.keys(t.tag_probs));
  const topTags = Object.entries(t.tag_probs)
    .filter(([tag]) => moodTags.has(tag))
    .sort((a, b) => b[1] - a[1])
    .slice(0, TOP_TAGS);
  const moods = Object.entries(t.mood_probs).sort((a, b) => b[1] - a[1]);
  const current = playhead === null ? null : segmentAt(t.segments.map((s) => s.start_s), playhead);

  return (
    <section aria-label="Track" className="track-page">
      <p>
        <Link to="/">← Map</Link>
      </p>
      <header className="track-head">
        <h2>{t.title ?? "Untitled"}</h2>
        <p className="secondary">
          {t.artist ?? "Unknown artist"}
          {t.album ? ` — ${t.album}` : ""}
        </p>
        {t.valence != null && t.arousal != null && (
          <p className="num">
            <strong>{t.octant}</strong>{" "}
            <span className="secondary">
              valence {signed(t.valence)} · arousal {signed(t.arousal)}
            </span>
          </p>
        )}
        {t.status !== "analyzed" && (
          <p role="alert">
            Not analyzed ({t.status}){t.error ? `: ${t.error}` : ""}
          </p>
        )}
      </header>

      {audioUrl && !audioError ? (
        <audio
          ref={audioRef}
          controls
          preload="metadata"
          src={audioUrl}
          onTimeUpdate={(e) => setPlayhead(e.currentTarget.currentTime)}
          onError={() => setAudioError(true)}
          className="player"
        />
      ) : (
        <p className="muted small">
          {audioError ? "The audio file could not be played." : "Audio playback is available when self-hosting Moody."}
        </p>
      )}

      <div className="track-grid">
        <div className="track-col">
          <div className="card">
            <TrajectoryChart
              segments={t.segments}
              duration={t.duration_s}
              playhead={playhead}
              onSeek={
                audioUrl && !audioError
                  ? (time) => {
                      if (audioRef.current) audioRef.current.currentTime = time;
                      setPlayhead(time);
                    }
                  : undefined
              }
            />
          </div>
          <div className="card">
            <Bars label="Mood classifiers" items={moods} />
          </div>
          <div className="card">
            <h2 className="small-heading">Audio facts</h2>
            <dl className="facts num">
              <div><dt>Tempo</dt><dd>{t.bpm != null ? `${t.bpm.toFixed(0)} BPM` : "—"}</dd></div>
              <div><dt>Key</dt><dd>{t.key ? `${t.key} ${t.scale ?? ""}` : "—"}</dd></div>
              <div><dt>Loudness</dt><dd>{t.loudness_lufs != null ? `${t.loudness_lufs.toFixed(1)} LUFS` : "—"}</dd></div>
              <div><dt>Length</dt><dd>{t.duration_s != null ? clock(t.duration_s) : "—"}</dd></div>
            </dl>
          </div>
          <section className="card" aria-label="Similar tracks">
            <h2 className="small-heading">Sounds similar</h2>
            {near.data && near.data.length > 0 ? (
              <ol className="neighbors">
                {near.data.map((n) => (
                  <li key={n.id}>
                    <Link to="/track/$trackId" params={{ trackId: String(n.id) }}>
                      {n.title ?? "Untitled"}
                    </Link>{" "}
                    <span className="secondary">{n.artist ?? ""}</span>{" "}
                    <span className="muted num">
                      {n.octant} · {Math.round(n.similarity * 100)}%
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="muted">{near.isPending ? "Loading…" : "No similar tracks yet."}</p>
            )}
          </section>
        </div>
        <div className="track-col">
          <div className="card">
            {t.valence != null && t.arousal != null && (
              <MiniCircumplex valence={t.valence} arousal={t.arousal} segments={t.segments} current={current} />
            )}
          </div>
          <div className="card">
            <Bars label="Top mood tags" items={topTags} />
          </div>
          <ThesisCard track={t} />
        </div>
      </div>
    </section>
  );
}

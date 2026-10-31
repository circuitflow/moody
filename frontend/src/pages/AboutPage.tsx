/** What Moody is and how well it works, from the committed evaluation results. */
import { Link } from "@tanstack/react-router";
import { evaluation, type Evaluation, type OctantStats } from "../features/about/evaluation";

const REPO = "https://github.com/circuitflow/moody";
const pct = (x: number) => `${Math.round(x * 100)}%`;
const signed = (x: number | null) => (x == null ? "–" : (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(2));

export function AboutPage({ data = evaluation }: { data?: Evaluation }) {
  const { deam, tags } = data;
  return (
    <section aria-label="About" className="about-page">
      <div className="card">
        <h2>About Moody</h2>
        <p>
          Moody places every song in a two-dimensional mood space: <strong>valence</strong> (unpleasant → pleasant)
          and <strong>arousal</strong> (calm → energetic), Russell's circumplex. It hears the audio itself, using
          pretrained deep models from Essentia: MSD-MusiCNN embeddings for valence/arousal and Discogs-EffNet for
          mood tags and similarity. It rebuilds a 2007 MIT thesis, whose hand-built features and decision tree you
          can still compare on every track page.
        </p>
        <p>
          <Link to="/path">Mood paths</Link> turn the map into playlists. Self-hosted, Moody also exports to
          Spotify and shows the mood of your listening history.{" "}
          <a href={REPO}>Source and setup on GitHub</a>.
        </p>
      </div>

      <div className="card">
        <h3>How well it works</h3>
        {deam ? (
          <>
            <div className="stat-row">
              <Stat label="Valence vs listeners" value={deam.valence_r.toFixed(2)} note={`Pearson r, ${deam.n} DEAM clips`} />
              <Stat label="Arousal vs listeners" value={deam.arousal_r.toFixed(2)} note="Pearson r" />
              {tags && (
                <Stat label="Mood tags" value={tags.macro_roc_auc.toFixed(2)} note={`macro ROC-AUC, ${tags.tracks} tracks`} />
              )}
              {deam.octants && (
                <Stat
                  label="Right octant, 2026 vs 2007"
                  value={`${pct(deam.octants.clear["2026_head"].exact)} vs ${pct(deam.octants.clear["2007_tree"].exact)}`}
                  note="DEAM clips away from neutral"
                />
              )}
            </div>
            <p className="note muted">
              The valence/arousal head was trained on DEAM, so those numbers are in-domain and optimistic. Its two
              outputs lean on one "intensity" axis: they correlate {signed(deam.predicted_va_corr)}, against{" "}
              {signed(deam.rated_va_corr)} between listeners' ratings. Loudness correlates{" "}
              {signed(deam.loudness_vs_v_minus_a.model)} with predicted valence minus arousal but{" "}
              {signed(deam.loudness_vs_v_minus_a.listeners)} with rated, so loud music looks happier to the model
              than to people.
            </p>
          </>
        ) : (
          <p className="muted">No evaluation results yet.</p>
        )}

        {deam?.octants && (
          <>
            <h4>2007 thesis vs 2026, on Russell's eight octants</h4>
            <table className="eval-table">
              <thead>
                <tr>
                  <th scope="col">Model</th>
                  <th scope="col">Exact octant</th>
                  <th scope="col">Within one</th>
                  <th scope="col">Mean angle error</th>
                </tr>
              </thead>
              <tbody>
                <OctantRow name="2026: DEAM head" s={deam.octants.clear["2026_head"]} />
                <OctantRow name="2007: decision tree" s={deam.octants.clear["2007_tree"]} />
                <tr>
                  <th scope="row">Most common octant, always</th>
                  <td className="num">{pct(deam.octants.clear.chance_exact)}</td>
                  <td />
                  <td />
                </tr>
              </tbody>
            </table>
            <p className="note muted">{deam.octants.note}</p>
          </>
        )}

        {tags && (
          <>
            <h4>Mood/theme tags (MTG-Jamendo test tracks)</h4>
            <table className="eval-table">
              <thead>
                <tr>
                  <th scope="col">Tag</th>
                  <th scope="col">ROC-AUC</th>
                  <th scope="col">PR-AUC</th>
                  <th scope="col">Share of tracks</th>
                </tr>
              </thead>
              <tbody>
                {[...tags.best, ...tags.worst].map((t, i) => (
                  <tr key={`${t.tag}-${i}`} className={i === tags.best.length ? "eval-split" : undefined}>
                    <th scope="row">{t.tag}</th>
                    <td className="num">{t.roc_auc.toFixed(2)}</td>
                    <td className="num">{t.pr_auc.toFixed(2)}</td>
                    <td className="num">{pct(t.prevalence)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="note muted">
              The five easiest and five hardest of {tags.tags_evaluated} tags. ROC-AUC doesn't depend on how common a tag
              is; compare PR-AUC with the share of tracks.
            </p>
          </>
        )}
        <p className="note">
          Details and method: <a href={`${REPO}/tree/main/eval/results`}>eval/results</a>. Music credits:{" "}
          <Link to="/credits">Credits</Link>.
        </p>
      </div>
    </section>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value num">{value}</span>
      <span className="muted stat-note">{note}</span>
    </div>
  );
}

function OctantRow({ name, s }: { name: string; s: OctantStats }) {
  return (
    <tr>
      <th scope="row">{name}</th>
      <td className="num">{pct(s.exact)}</td>
      <td className="num">{pct(s.within_one)}</td>
      <td className="num">{Math.round(s.mean_angle_error_deg)}°</td>
    </tr>
  );
}

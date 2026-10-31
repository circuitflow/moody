/** Credits for the demo's CC-licensed music (static demo); a note when self-hosting. */
import { Link } from "@tanstack/react-router";
import { useCredits } from "../data/hooks";

export function CreditsPage() {
  const credits = useCredits();
  if (credits.isPending) return <p className="muted">Loading…</p>;
  const list = credits.data ?? [];
  if (list.length === 0) {
    return <p className="card">No credits: this library is your own music.</p>;
  }
  const licences = new Map<string, number>();
  for (const c of list) licences.set(c.license, (licences.get(c.license) ?? 0) + 1);
  return (
    <section aria-label="Credits" className="card credits">
      <h2>Music credits</h2>
      <p>
        The demo's {list.length.toLocaleString()} tracks come from{" "}
        <a href="https://www.jamendo.com" target="_blank" rel="noreferrer">
          Jamendo
        </a>{" "}
        via the{" "}
        <a href="https://mtg.github.io/mtg-jamendo-dataset/" target="_blank" rel="noreferrer">
          MTG-Jamendo dataset
        </a>{" "}
        (mood/theme test split), under Creative Commons licences that allow sharing with credit (
        {[...licences].map(([name, n]) => `${name}: ${n}`).join(", ")}). Audio streams from Jamendo; Moody
        only stores the analysis.
      </p>
      <table className="credits-table">
        <thead>
          <tr>
            <th scope="col">Track</th>
            <th scope="col">Artist</th>
            <th scope="col">Licence</th>
          </tr>
        </thead>
        <tbody>
          {list.map((c) => (
            <tr key={c.id}>
              <td>
                <Link to="/track/$trackId" params={{ trackId: String(c.id) }}>
                  {c.title}
                </Link>{" "}
                <a href={c.url} target="_blank" rel="noreferrer" aria-label={`${c.title} on Jamendo`}>
                  ↗
                </a>
              </td>
              <td>{c.artist}</td>
              <td>
                <a href={c.license_url} target="_blank" rel="noreferrer license">
                  {c.license}
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

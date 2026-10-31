import { Link, Outlet } from "@tanstack/react-router";
import { useDataSource } from "../data/context";
import { useCredits, useMeta } from "../data/hooks";
import { ScanControl } from "./ScanControl";
import { ThemeToggle } from "./ThemeToggle";

export function Shell() {
  const meta = useMeta();
  const source = useDataSource();
  const credits = useCredits();
  const demoTracks = source.kind === "static" ? (credits.data?.length ?? 0) : 0;
  return (
    <div className="shell">
      {demoTracks > 0 && (
        <p className="demo-banner" role="note">
          Demo: {demoTracks.toLocaleString()} Creative Commons tracks from Jamendo, analyzed by Moody.{" "}
          <Link to="/credits">Credits</Link> ·{" "}
          <a href="https://github.com/circuitflow/moody#quick-start-self-hosted">Run it on your own music</a>
        </p>
      )}
      <header className="shell-header">
        <h1>Moody</h1>
        <nav aria-label="Views">
          <Link to="/">Map</Link>
          <Link to="/list">List</Link>
          <Link to="/path">Path</Link>
          {source.canSave && <Link to="/playlists">Playlists</Link>}
          {source.canSave && <Link to="/history">History</Link>}
        </nav>
        <span className="spacer" />
        <ThemeToggle />
      </header>
      <main>
        <Outlet />
      </main>
      <footer className="shell-footer">
        <span role="status">
          {meta.isPending && "Loading library…"}
          {meta.isError && "Library unavailable"}
          {meta.isSuccess &&
            `${meta.data.analyzed} of ${meta.data.tracks} tracks analyzed · ` +
              `${source.kind === "static" ? "demo" : "v" + meta.data.version} · ` +
              `pipeline ${meta.data.pipeline_version}` +
              (meta.data.duplicates ? ` · ${meta.data.duplicates} duplicate files hidden` : "")}
        </span>
        {meta.data?.can_scan && <ScanControl />}
      </footer>
    </div>
  );
}

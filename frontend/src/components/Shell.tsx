import { Link, Outlet } from "@tanstack/react-router";
import { useDataSource } from "../data/context";
import { useMeta } from "../data/hooks";
import { ThemeToggle } from "./ThemeToggle";

export function Shell() {
  const meta = useMeta();
  const source = useDataSource();
  return (
    <div className="shell">
      <header className="shell-header">
        <h1>Moody</h1>
        <nav aria-label="Views">
          <Link to="/">Map</Link>
          <Link to="/list">List</Link>
          <Link to="/path">Path</Link>
        </nav>
        <span className="spacer" />
        <ThemeToggle />
      </header>
      <main>
        <Outlet />
      </main>
      <footer className="shell-footer" role="status">
        {meta.isPending && "Loading library…"}
        {meta.isError && "Library unavailable"}
        {meta.isSuccess &&
          `${meta.data.analyzed} of ${meta.data.tracks} tracks analyzed · ` +
            `${source.kind === "static" ? "demo" : "v" + meta.data.version} · ` +
            `pipeline ${meta.data.pipeline_version}` +
            (meta.data.duplicates ? ` · ${meta.data.duplicates} duplicate files hidden` : "")}
      </footer>
    </div>
  );
}

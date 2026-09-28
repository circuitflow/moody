import { useQuery } from "@tanstack/react-query";
import { useDataSource } from "./data/context";
import { Circumplex } from "./components/Circumplex";

export function App() {
  const source = useDataSource();
  const health = useQuery({ queryKey: ["health"], queryFn: () => source.health() });

  return (
    <main className="app">
      <header>
        <h1>Moody</h1>
        <p className="tagline">The mood of your music library, mapped.</p>
      </header>
      <Circumplex />
      <footer>
        <span role="status">
          {health.isPending && "Connecting…"}
          {health.isError && "Backend unavailable"}
          {health.isSuccess && `${source.kind === "static" ? "Demo" : "Backend"} v${health.data.version}`}
        </span>
      </footer>
    </main>
  );
}

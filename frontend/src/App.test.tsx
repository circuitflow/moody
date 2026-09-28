import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { App } from "./App";
import { DataSourceProvider } from "./data/context";
import type { DataSource } from "./data/source";

function renderWith(source: DataSource) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DataSourceProvider source={source}>
        <App />
      </DataSourceProvider>
    </QueryClientProvider>,
  );
}

test("shows backend version when healthy", async () => {
  renderWith({ kind: "api", health: async () => ({ status: "ok", version: "1.2.3" }) });
  expect(await screen.findByText("Backend v1.2.3")).toBeInTheDocument();
  expect(screen.getByRole("img", { name: /valence–arousal/i })).toBeInTheDocument();
});

test("reports an unavailable backend", async () => {
  renderWith({ kind: "api", health: () => Promise.reject(new Error("down")) });
  expect(await screen.findByText("Backend unavailable")).toBeInTheDocument();
});

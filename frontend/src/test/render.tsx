import { QueryClient } from "@tanstack/react-query";
import { createMemoryHistory } from "@tanstack/react-router";
import { render } from "@testing-library/react";
import { App } from "../App";
import type { DataSource } from "../data/source";
import { FakeSource } from "./fakeSource";

/** Render the whole app at `path` against a fake data source. */
export function renderApp(path = "/", source: DataSource = new FakeSource()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const history = createMemoryHistory({ initialEntries: [path] });
  return render(<App source={source} history={history} queryClient={queryClient} />);
}

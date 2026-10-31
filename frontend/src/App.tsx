import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, type RouterHistory } from "@tanstack/react-router";
import { useState } from "react";
import { DataSourceProvider } from "./data/context";
import type { DataSource } from "./data/source";
import { createAppRouter } from "./router";
import { LibraryProvider } from "./state/library";

export function App({
  source,
  history,
  queryClient,
}: {
  source: DataSource;
  history?: RouterHistory;
  queryClient?: QueryClient;
}) {
  const [client] = useState(() => queryClient ?? new QueryClient());
  const [router] = useState(() => createAppRouter(history));
  return (
    <QueryClientProvider client={client}>
      <DataSourceProvider source={source}>
        <LibraryProvider>
          <RouterProvider router={router} />
        </LibraryProvider>
      </DataSourceProvider>
    </QueryClientProvider>
  );
}

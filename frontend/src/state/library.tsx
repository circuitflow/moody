/** Filters, color-by and selection shared by the map and the list view. */
import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { NO_FILTERS, type ColorBy, type Filters } from "./filters";

interface LibraryState {
  filters: Filters;
  setFilters: (f: Filters) => void;
  colorBy: ColorBy;
  setColorBy: (c: ColorBy) => void;
  selection: ReadonlySet<number>;
  setSelection: (ids: ReadonlySet<number>) => void;
}

const LibraryContext = createContext<LibraryState | null>(null);

export function LibraryProvider({ children }: { children: ReactNode }) {
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [colorBy, setColorBy] = useState<ColorBy>({ kind: "none" });
  const [selection, setSelection] = useState<ReadonlySet<number>>(new Set());
  const value = useMemo(
    () => ({ filters, setFilters, colorBy, setColorBy, selection, setSelection }),
    [filters, colorBy, selection],
  );
  return <LibraryContext.Provider value={value}>{children}</LibraryContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useLibrary(): LibraryState {
  const state = useContext(LibraryContext);
  if (!state) throw new Error("useLibrary must be used inside <LibraryProvider>");
  return state;
}

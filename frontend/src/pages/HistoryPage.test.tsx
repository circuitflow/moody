import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { FakeSource } from "../test/fakeSource";
import { renderApp } from "../test/render";

function withHistory() {
  const source = new FakeSource();
  source.history = {
    plays: 1200, matched: 300, lastfm_configured: true, lastfm_user: "owen", spotify_connected: true,
    sources: [{ source: "lastfm", plays: 1200, matched: 300, first: "2025-01-06T10:00:00Z", last: "2025-10-27T10:00:00Z" }],
  };
  source.mood.week = [
    { key: "2025-10-13", plays: 40, matched: 10, valence: 0.12, arousal: 0.3 },
    { key: "2025-10-20", plays: 5, matched: 0, valence: null, arousal: null },
    { key: "2025-10-27", plays: 30, matched: 12, valence: -0.05, arousal: 0.2 },
  ];
  source.mood.hour = Array.from({ length: 24 }, (_, h) => ({
    key: String(h), plays: 10, matched: h < 6 ? 0 : 3, valence: h < 6 ? null : 0.1, arousal: h < 6 ? null : 0.2,
  }));
  source.top = [
    { id: 1, title: "Happy Song", artist: "Band A", album: null, duration_s: 200, status: "analyzed",
      valence: 0.5, arousal: 0.4, octant: "Excitement", top_tags: [], plays: 42 },
  ];
  return source;
}

test("shows coverage, both mood charts with tables, and the most played", async () => {
  renderApp("/history", withHistory());
  const tile = (await screen.findByText("Plays imported")).closest<HTMLElement>(".stat")!;
  expect(within(tile).getByText("1,200")).toBeInTheDocument();
  expect(screen.getByText("25%")).toBeInTheDocument();
  const week = await screen.findByRole("img", { name: /^Mood by week/ });
  expect(week.querySelectorAll("path.series")).toHaveLength(2);
  // The empty week breaks the line into two pieces, each a lone point with a dot.
  expect(week.querySelector("path.series")!.getAttribute("d")!.match(/M/g)).toHaveLength(2);
  const weekTable = screen.getAllByRole("table")[0]!;
  expect(within(weekTable).getAllByRole("row")).toHaveLength(4);
  expect(within(weekTable).getByText("−0.05")).toBeInTheDocument();
  expect(screen.getByRole("img", { name: /^Mood by hour of day/ })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Happy Song" })).toBeInTheDocument();
  expect(screen.getByText(/42 plays/)).toBeInTheDocument();
});

test("periods refetch the charts in the browser's time zone", async () => {
  const source = withHistory();
  renderApp("/history", source);
  fireEvent.click(await screen.findByRole("button", { name: "Last 3 months" }));
  await waitFor(() => expect(source.moodRequests.some((r) => r.startsWith("week ") && r.endsWith(" quarter"))).toBe(true));
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  expect(source.moodRequests[0]).toBe(`week ${tz} all`);
});

test("Last.fm import keeps going while there's more", async () => {
  const source = withHistory();
  source.lastfmRuns = [
    { source: "lastfm", new: 2000, duplicates: 0, skipped: 0, more: true, plays: 3200, matched: 500 },
    { source: "lastfm", new: 150, duplicates: 3, skipped: 1, more: false, plays: 3350, matched: 520 },
  ];
  renderApp("/history", source);
  fireEvent.click(await screen.findByRole("button", { name: "Import from Last.fm" }));
  expect(await screen.findByText(/2,150 new plays \(3 already imported\)\. 520 of 3,350 plays now match/)).toBeInTheDocument();
  expect(source.lastfmCalls).toBe(2);
});

test("import errors are shown", async () => {
  renderApp("/history", withHistory());
  fireEvent.change(await screen.findByLabelText("Last.fm user"), { target: { value: "nobody" } });
  fireEvent.click(screen.getByRole("button", { name: "Import from Last.fm" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("User not found");
});

test("an empty history explains how to start", async () => {
  renderApp("/history");
  expect(await screen.findByText(/moody history spotify-export/)).toBeInTheDocument();
  expect(screen.queryByRole("group", { name: "Period" })).toBeNull();
  expect(screen.getByRole("link", { name: "History" })).toBeInTheDocument();
});

test("the static demo has no history", async () => {
  class StaticFake extends FakeSource {
    override readonly canSave = false;
  }
  renderApp("/history", new StaticFake());
  expect(await screen.findByText(/needs the self-hosted app/)).toBeInTheDocument();
});

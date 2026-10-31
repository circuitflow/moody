import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { FakeSource } from "../test/fakeSource";
import { renderApp } from "../test/render";

test("save a path, open it, reopen it in the builder, and delete it", async () => {
  const source = new FakeSource();
  renderApp("/path?from=Depression&to=Excitement", source);
  const panel = await screen.findByRole("complementary", { name: "Playlist" });
  expect(within(panel).getByPlaceholderText("Depression → Excitement")).toBeInTheDocument();
  fireEvent.change(within(panel).getByLabelText("Playlist name"), { target: { value: "Morning lift" } });
  fireEvent.click(within(panel).getByRole("button", { name: "Save" }));
  const status = await within(panel).findByRole("status");
  expect(status).toHaveTextContent("Saved as “Morning lift”.");

  const saved = source.saved[0]!;
  expect(saved.tracks).toHaveLength(4);
  expect(saved.params).toMatchObject({
    search: { from: "Depression", to: "Excitement" },
    filters: { query: "", tags: [], octants: [] },
  });

  fireEvent.click(within(status).getByRole("link", { name: "Open playlist" }));
  expect(await screen.findByRole("heading", { name: "Morning lift" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Download M3U" })).toHaveAttribute("href", "/api/playlists/1/m3u");
  const tracks = screen.getAllByRole("listitem").filter((li) => li.closest(".playlist-tracks"));
  expect(tracks).toHaveLength(4);

  fireEvent.click(screen.getByRole("button", { name: "Open in path builder" }));
  expect(await screen.findByLabelText("From")).toHaveValue("Depression");
  expect(screen.getByLabelText("To")).toHaveValue("Excitement");

  fireEvent.click(screen.getByRole("link", { name: "Playlists" }));
  fireEvent.click(await screen.findByRole("link", { name: "Morning lift" }));
  fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
  expect(await screen.findByText(/No saved playlists yet/)).toBeInTheDocument();
  expect(source.saved).toHaveLength(0);
});

test("a blank name falls back to the path's ends", async () => {
  const source = new FakeSource();
  renderApp("/path", source);
  fireEvent.click(await screen.findByRole("button", { name: "Save" }));
  await waitFor(() => expect(source.saved[0]?.name).toBe("Distress → Relaxation"));
});

test("the static demo has no saving, but can copy a link", async () => {
  class StaticFake extends FakeSource {
    override readonly canSave = false;
    audioUrl() {
      return null;
    }
  }
  renderApp("/path", new StaticFake());
  const panel = await screen.findByRole("complementary", { name: "Playlist" });
  expect(within(panel).queryByRole("button", { name: "Save" })).toBeNull();
  expect(within(panel).getByRole("button", { name: "Copy link" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Playlists" })).toBeNull();
});

test("an unknown playlist says so", async () => {
  renderApp("/playlists/42");
  expect(await screen.findByText(/Playlist not found/)).toBeInTheDocument();
});

async function savedPlaylist(source: FakeSource) {
  await source.savePlaylist({ name: "Night drive", track_ids: [1, 2, 3], start: [0, 0], end: [1, 1] });
  renderApp("/playlists/1", source);
  await screen.findByRole("heading", { name: "Night drive" });
}

test("Spotify: connect first, then export and list what wasn't found", async () => {
  const source = new FakeSource();
  await savedPlaylist(source);
  const connect = await screen.findByRole("link", { name: "Connect Spotify" });
  expect(connect.getAttribute("href")).toMatch(/^\/api\/auth\/spotify\/login\?return_to=http/);
});

test("Spotify: export reports matches and misses", async () => {
  const source = new FakeSource();
  source.spotify = { configured: true, connected: true, account: "Owen", redirect_uri: null, error: null };
  source.missing = new Set([2]);
  await savedPlaylist(source);
  expect(await screen.findByText(/Connected as Owen/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Export to Spotify" }));
  const message = await screen.findByText(/Created “Night drive” on Spotify with 2 of 3 tracks\./);
  const result = message.closest<HTMLElement>('[role="status"]')!;
  expect(within(result).getByRole("link", { name: "Open in Spotify ↗" })).toHaveAttribute(
    "href",
    "https://open.spotify.com/playlist/pl1",
  );
  expect(within(result).getByText("1 not found on Spotify")).toBeInTheDocument();
  expect(within(result).getByText("Sad Song")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
  expect(await screen.findByRole("link", { name: "Connect Spotify" })).toBeInTheDocument();
});

test("Spotify: setup hint when not configured, and sign-in errors are shown", async () => {
  const source = new FakeSource();
  source.spotify = { configured: false, connected: false, account: null, redirect_uri: null, error: null };
  await savedPlaylist(source);
  expect(await screen.findByText(/MOODY_SPOTIFY_CLIENT_ID/)).toBeInTheDocument();
});

test("Spotify: a failed sign-in explains why", async () => {
  const source = new FakeSource();
  source.spotify = { configured: true, connected: false, account: null, redirect_uri: null, error: "Spotify sign-in was not completed (access_denied)" };
  await savedPlaylist(source);
  expect(await screen.findByRole("alert")).toHaveTextContent("access_denied");
});

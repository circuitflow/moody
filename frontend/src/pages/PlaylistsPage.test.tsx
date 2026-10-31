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

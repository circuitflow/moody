import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, vi } from "vitest";
import { renderApp } from "../test/render";

beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(() => Promise.resolve());
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
});

const titles = () =>
  within(screen.getByRole("complementary", { name: "Playlist" }))
    .getAllByRole("listitem")
    .map((li) => within(li).getByRole("link").textContent);

test("walks from Distress to Relaxation by default", async () => {
  renderApp("/path");
  await screen.findByRole("complementary", { name: "Playlist" });
  const list = titles();
  expect(list).toHaveLength(4); // only 4 tracks in the library
  expect(list[0]).toBe("Angry Song");
  expect(list[3]).toBe("Calm Song");
  expect(screen.getByText(/Only 4 tracks match the filters/)).toBeInTheDocument();
  // Band A has two of the four tracks, so they can't be 3 apart.
  expect(screen.getByText(/some artists repeat within three tracks/)).toBeInTheDocument();
});

test("the endpoints come from the URL, and the pickers change them", async () => {
  renderApp("/path?from=Depression&to=Excitement&n=5");
  await screen.findByRole("complementary", { name: "Playlist" });
  await waitFor(() => expect(titles()[0]).toBe("Sad Song"));
  expect(titles()[3]).toBe("Happy Song");
  fireEvent.change(screen.getByLabelText("To"), { target: { value: "Distress" } });
  // Distress is up and to the left: negative valence, positive arousal.
  expect(await screen.findByRole("button", { name: /^End: valence −0\.\d+, arousal \+0\.\d+/ })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Swap start and end" }));
  await waitFor(() => expect(screen.getByLabelText("From")).toHaveValue("Distress"));
  expect(screen.getByLabelText("To")).toHaveValue("Depression");
  await waitFor(() => expect(titles()[0]).toBe("Angry Song"));
});

test("handles move with the arrow keys, and the path follows", async () => {
  renderApp("/path?from=Depression&to=Excitement");
  const start = await screen.findByRole("button", { name: /^Start: valence/ });
  const before = start.getAttribute("aria-label");
  fireEvent.keyDown(start, { key: "ArrowRight", shiftKey: true });
  await waitFor(() =>
    expect(screen.getByRole("button", { name: /^Start: valence/ }).getAttribute("aria-label")).not.toBe(before),
  );
  expect(screen.getByLabelText("From")).toHaveValue(""); // now a custom point
});

test("bending adds a via point, and filters limit the playlist", async () => {
  renderApp("/path");
  fireEvent.click(await screen.findByLabelText(/Bend through a point/));
  expect(await screen.findByRole("button", { name: /^Via: valence/ })).toBeInTheDocument();
  const filters = screen.getByRole("group", { name: "Map filters" });
  fireEvent.click(within(filters).getByRole("button", { name: "happy" }));
  await waitFor(() => expect(titles()).toEqual(["Happy Song"]));
  expect(screen.getByText(/Only 1 track match the filters/)).toBeInTheDocument();
});

test("plays the playlist in order", async () => {
  renderApp("/path");
  fireEvent.click(await screen.findByRole("button", { name: "▶ Play all" }));
  expect(await screen.findByRole("button", { name: "■ Stop" })).toBeInTheDocument();
  const items = within(screen.getByRole("complementary", { name: "Playlist" })).getAllByRole("listitem");
  expect(items[0]).toHaveAttribute("aria-current", "true");
  expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
});

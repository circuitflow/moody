import { fireEvent, screen, within } from "@testing-library/react";
import { FakeSource } from "../test/fakeSource";
import { renderApp } from "../test/render";

test("filters update the visible count", async () => {
  renderApp("/");
  expect(await screen.findByText("Showing 4 of 4 tracks")).toBeInTheDocument();
  const tags = screen.getByRole("group", { name: "Map filters" });
  fireEvent.click(within(tags).getByRole("button", { name: "happy" }));
  expect(await screen.findByText("Showing 1 of 4 tracks")).toBeInTheDocument();
  fireEvent.click(within(tags).getByRole("button", { name: "Clear filters" }));
  fireEvent.change(screen.getByLabelText("Search title or artist"), { target: { value: "band a" } });
  expect(await screen.findByText("Showing 2 of 4 tracks")).toBeInTheDocument();
});

test("octant toggles filter by the 2026 octant", async () => {
  renderApp("/");
  const octants = await screen.findByLabelText("Octants");
  fireEvent.click(within(octants).getByRole("button", { name: "Excitement" }));
  expect(await screen.findByText("Showing 1 of 4 tracks")).toBeInTheDocument();
});

test("color by 2007 vs 2026 shows a categorical legend with counts", async () => {
  renderApp("/");
  fireEvent.change(await screen.findByLabelText(/Color by/), { target: { value: "agreement" } });
  const legend = await screen.findByLabelText("Legend: 2007 vs 2026 octant");
  // Happy: Excitement/Excitement = same; Calm: Relaxation vs Pleasure = adjacent;
  // Sad: Depression/Depression = same; Angry: Distress vs Relaxation = different.
  expect(within(legend).getByText("Same octant")).toBeInTheDocument();
  expect(within(legend).getByText("(2)")).toBeInTheDocument();
  expect(within(legend).getByText("2+ octants apart")).toBeInTheDocument();
});

test("color by a field shows a sequential legend", async () => {
  renderApp("/");
  fireEvent.change(await screen.findByLabelText(/Color by/), { target: { value: "bpm" } });
  expect(await screen.findByLabelText("Legend: Tempo (BPM)")).toBeInTheDocument();
});

test("empty library explains how to scan", async () => {
  renderApp("/", new FakeSource([]));
  expect(await screen.findByText(/No analyzed tracks yet/)).toBeInTheDocument();
});

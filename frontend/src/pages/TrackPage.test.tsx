import { fireEvent, screen, within } from "@testing-library/react";
import { FakeSource } from "../test/fakeSource";
import { renderApp } from "../test/render";

test("track page shows mood, charts, thesis card and neighbors", async () => {
  renderApp("/track/1");
  expect(await screen.findByRole("heading", { name: "Happy Song" })).toBeInTheDocument();
  expect(screen.getByRole("img", { name: /Valence and arousal over/ })).toBeInTheDocument();
  expect(screen.getByRole("img", { name: "Position on the mood circle" })).toBeInTheDocument();
  const moods = screen.getByLabelText("Mood classifiers");
  expect(within(moods).getByText("happy")).toBeInTheDocument();
  const thesis = screen.getByLabelText("2007 vs 2026");
  expect(within(thesis).getByText("“cheerful”")).toBeInTheDocument();
  expect(within(thesis).getByText("Same octant.")).toBeInTheDocument();
  expect(within(thesis).getByText("major")).toBeInTheDocument(); // mode 60 >= 50
  const near = await screen.findByLabelText("Similar tracks");
  expect(await within(near).findAllByRole("link")).toHaveLength(3);
  expect(document.querySelector("audio")?.getAttribute("src")).toBe("/api/audio/1");
  expect(screen.getByText(/Also in your library as MP3/)).toBeInTheDocument();
});

test("static source shows no player", async () => {
  class StaticFake extends FakeSource {
    audioUrl() {
      return null;
    }
  }
  renderApp("/track/2", new StaticFake());
  expect(await screen.findByText(/Audio playback is available when self-hosting/)).toBeInTheDocument();
});

test("unknown track shows an error with a way back", async () => {
  renderApp("/track/999");
  expect(await screen.findByText("Track not found.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "← Back to the map" })).toBeInTheDocument();
});

test("hovering the trajectory shows a readout", async () => {
  renderApp("/track/1");
  const chart = await screen.findByRole("img", { name: /Valence and arousal over/ });
  fireEvent.pointerMove(chart, { clientX: 10, clientY: 10 });
  expect(await screen.findByText(/valence$/)).toBeInTheDocument();
});

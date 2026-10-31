import { screen, within } from "@testing-library/react";
import { FakeSource } from "../test/fakeSource";
import { renderApp } from "../test/render";

class DemoFake extends FakeSource {
  override readonly kind = "static";
  override readonly canSave = false;
  audioUrl() {
    return null;
  }
}

function demoSource() {
  const source = new DemoFake();
  source.creditList = [
    { id: 1, title: "Happy Song", artist: "Band A", license: "CC BY 3.0", license_url: "https://cc/by/3.0/", url: "https://jamendo/1", audio_url: "https://stream/1" },
    { id: 2, title: "Sad Song", artist: "Band B", license: "CC BY-SA 4.0", license_url: "https://cc/by-sa/4.0/", url: "https://jamendo/2", audio_url: "https://stream/2" },
  ];
  return source;
}

function fullDemoSource() {
  const source = demoSource();
  source.creditList = [1, 2, 3, 4].map((id) => ({
    id, title: `T${id}`, artist: "A", license: "CC BY 3.0", license_url: "l", url: "u", audio_url: `https://stream/${id}`,
  }));
  return source;
}

test("the demo shows a banner and credits every track with its licence", async () => {
  renderApp("/credits", demoSource());
  const banner = await screen.findByRole("note");
  expect(banner).toHaveTextContent("Demo: 2 Creative Commons tracks from Jamendo");
  const table = await screen.findByRole("table");
  const rows = within(table).getAllByRole("row");
  expect(rows).toHaveLength(3);
  expect(within(rows[1]!).getByRole("link", { name: "CC BY 3.0" })).toHaveAttribute("href", "https://cc/by/3.0/");
  expect(screen.getByText(/CC BY 3.0: 1, CC BY-SA 4.0: 1/)).toBeInTheDocument();
});

test("the path player uses the Jamendo streams in the demo", async () => {
  renderApp("/path", fullDemoSource());
  expect(await screen.findByRole("button", { name: "▶ Play all" })).toBeInTheDocument();
});

test("self-hosted: no banner, and credits say it's your music", async () => {
  renderApp("/credits");
  expect(await screen.findByText(/this library is your own music/)).toBeInTheDocument();
  expect(screen.queryByRole("note")).toBeNull();
});

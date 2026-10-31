import { fireEvent, screen, within } from "@testing-library/react";
import { renderApp } from "../test/render";

const titles = () =>
  screen
    .getAllByRole("row")
    .slice(1)
    .map((r) => within(r).getAllByRole("cell")[0]!.textContent);

test("list shows every track sorted by title", async () => {
  renderApp("/list");
  expect(await screen.findByText("Showing 4 of 4 tracks")).toBeInTheDocument();
  expect(titles()).toEqual(["Angry Song", "Calm Song", "Happy Song", "Sad Song"]);
});

test("sorting by valence toggles direction", async () => {
  renderApp("/list");
  const header = await screen.findByRole("button", { name: "Valence" });
  fireEvent.click(header);
  expect(titles()).toEqual(["Angry Song", "Sad Song", "Calm Song", "Happy Song"]);
  expect(screen.getByRole("columnheader", { name: /Valence/ })).toHaveAttribute("aria-sort", "ascending");
  fireEvent.click(screen.getByRole("button", { name: /Valence/ }));
  expect(titles()[0]).toBe("Happy Song");
});

test("filters are shared with the map controls", async () => {
  renderApp("/list");
  const filters = await screen.findByRole("group", { name: "Map filters" });
  expect(within(filters).queryByLabelText(/Color by/)).toBeNull(); // map-only control
  fireEvent.click(within(filters).getByRole("button", { name: "sad" }));
  expect(await screen.findByText("Showing 1 of 4 tracks")).toBeInTheDocument();
  expect(titles()).toEqual(["Sad Song"]);
});

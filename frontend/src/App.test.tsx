import { screen } from "@testing-library/react";
import { renderApp } from "./test/render";

test("shell shows library counts from meta", async () => {
  renderApp("/");
  expect(await screen.findByText(/4 of 4 tracks analyzed/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Map" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "List" })).toBeInTheDocument();
});

test("routes to a track page", async () => {
  renderApp("/track/2");
  expect(await screen.findByLabelText("Track")).toBeInTheDocument();
});

test("theme toggle cycles and sets data-theme", async () => {
  renderApp("/");
  const button = await screen.findByRole("button", { name: /Theme: system/ });
  button.click();
  expect(await screen.findByRole("button", { name: /Theme: light/ })).toBeInTheDocument();
  expect(document.documentElement.dataset.theme).toBe("light");
});

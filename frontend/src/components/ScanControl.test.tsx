import { fireEvent, screen } from "@testing-library/react";
import { FakeSource, fakeJob } from "../test/fakeSource";
import { renderApp } from "../test/render";

test("scan library shows progress, then the result", async () => {
  const source = new FakeSource();
  source.canScan = true;
  source.jobUpdates = [
    fakeJob({ total: 0 }),
    fakeJob({ total: 10, progress: 4 }),
    fakeJob({ status: "completed", total: 10, progress: 10, failed: 1 }),
  ];
  renderApp("/", source);
  fireEvent.click(await screen.findByRole("button", { name: "Scan library" }));
  expect(await screen.findByText("Looking for new and changed files…")).toBeInTheDocument();
  expect(await screen.findByRole("progressbar", { name: "Scan progress" })).toHaveAttribute("value", "4");
  expect(await screen.findByText("4 of 10")).toBeInTheDocument();
  expect(await screen.findByText("Scan finished: 9 analyzed, 1 failed.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Scan library" })).toBeEnabled();
  expect(source.scansStarted).toBe(1);
});

test("a scan already running is picked up after a reload", async () => {
  const source = new FakeSource();
  source.canScan = true;
  source.runningJob = fakeJob({ total: 20, progress: 5 });
  source.jobUpdates = [fakeJob({ status: "failed", total: 20, progress: 5, error: "disk unplugged" })];
  renderApp("/", source);
  expect(await screen.findByRole("button", { name: "Scanning…" })).toBeDisabled();
  expect(await screen.findByRole("alert")).toHaveTextContent("Scan failed: disk unplugged");
});

test("no scan control without a configured library", async () => {
  renderApp("/");
  await screen.findByText(/tracks analyzed/);
  expect(screen.queryByRole("button", { name: "Scan library" })).toBeNull();
});

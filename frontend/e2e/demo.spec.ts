import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  page.on("pageerror", (err) => {
    throw err;
  });
});

test("the demo credits every track and plays its stream", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("note")).toContainText("Demo: 40 Creative Commons tracks from Jamendo");
  await page.getByRole("note").getByRole("link", { name: "Credits" }).click();
  await expect(page.getByRole("table").getByRole("row")).toHaveCount(41);
  await page.getByRole("table").getByRole("link", { name: "Track 05", exact: true }).click();
  await expect(page.getByText(/“Track 05” by Artist 5, CC BY 3\.0, on Jamendo/)).toBeVisible();
  // The audio element loads the stream (here a local WAV standing in for Jamendo).
  const audio = page.locator("audio");
  await expect(audio).toHaveAttribute("src", /data\/audio\/1005\.wav$/);
  await expect.poll(() => audio.evaluate((a: HTMLAudioElement) => a.readyState)).toBeGreaterThan(0);
});

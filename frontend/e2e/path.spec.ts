import { expect, test, type Page } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  page.on("pageerror", (err) => {
    throw err;
  });
});

const playlist = (page: Page) => page.getByRole("complementary", { name: "Playlist" }).getByRole("listitem");

test("builds a 20-track path from Distress to Relaxation in the static demo", async ({ page }) => {
  await page.goto("/#/path");
  await expect(playlist(page)).toHaveCount(20);
  await expect(page.getByLabel("From")).toHaveValue("Distress");
  await expect(page.getByLabel("To")).toHaveValue("Relaxation");
  await expect(page.locator(".path-numbers text")).toHaveCount(20);
  await expect(page.locator(".path-target")).toHaveCount(1);
  // The demo can't save, but a path is shareable as a link.
  await expect(page.getByRole("button", { name: "Save" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Copy link" })).toBeVisible();
});

test("dragging the end point re-plans and updates the link", async ({ page }) => {
  await page.goto("/#/path?n=10");
  const before = await playlist(page).allTextContents();
  const end = page.getByRole("button", { name: /^End: valence/ });
  const box = (await end.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x - 60, box.y - 260, { steps: 10 });
  await page.mouse.up();
  await expect(page).toHaveURL(/to=-?\d\.\d{3}%2C-?\d\.\d{3}/);
  await expect(page.getByLabel("To")).toHaveValue("");
  await expect(playlist(page)).toHaveCount(10);
  expect(await playlist(page).allTextContents()).not.toEqual(before);
});

test("keyboard moves a handle", async ({ page }) => {
  await page.goto("/#/path?n=6");
  const start = page.getByRole("button", { name: /^Start: valence/ });
  const label = await start.getAttribute("aria-label");
  await start.focus();
  await page.keyboard.press("Shift+ArrowUp");
  await expect(page.getByRole("button", { name: /^Start: valence/ })).not.toHaveAttribute("aria-label", label!);
  await expect(page).toHaveURL(/from=/);
});

test("deep links restore the path, and a track page leads back to it", async ({ page }) => {
  await page.goto("/#/path?from=Sleepiness&to=Excitement&n=8&s=0");
  await expect(playlist(page)).toHaveCount(8);
  await expect(page.getByLabel("From")).toHaveValue("Sleepiness");
  const first = await playlist(page).first().getByRole("link").textContent();
  await page.reload();
  await expect(playlist(page).first().getByRole("link")).toHaveText(first!);
  await playlist(page).first().getByRole("link").click();
  await expect(page.getByRole("heading", { level: 2, name: first! })).toBeVisible();
  await page.goBack();
  await expect(page.getByLabel("To")).toHaveValue("Excitement");
  await expect(playlist(page)).toHaveCount(8);
});

test("copy link puts the shareable URL on the clipboard", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/#/path?from=Depression&to=Pleasure&n=5");
  await page.getByRole("button", { name: "Copy link" }).click();
  await expect(page.getByRole("button", { name: "Link copied" })).toBeVisible();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toContain("#/path?");
  expect(copied).toContain("from=Depression");
});

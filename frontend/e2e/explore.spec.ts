import { expect, test, type Page } from "@playwright/test";

/** Sweep the pointer across the map until the nearest-point tooltip appears. */
async function hoverAnyPoint(page: Page) {
  const box = (await page.getByTestId("map-overlay").boundingBox())!;
  for (let fy = 0.2; fy <= 0.8; fy += 0.1) {
    for (let fx = 0.1; fx <= 0.9; fx += 0.05) {
      await page.mouse.move(box.x + box.width * fx, box.y + box.height * fy);
      if (await page.getByRole("tooltip").isVisible()) return;
    }
  }
  throw new Error("no map point found under the pointer sweep");
}

test.beforeEach(async ({ page }) => {
  page.on("pageerror", (err) => {
    throw err;
  });
});

test("map shows the whole library and a hover tooltip", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Showing 40 of 40 tracks")).toBeVisible();
  await expect(page.getByText("40 of 40 tracks analyzed")).toBeVisible();
  await hoverAnyPoint(page);
  await expect(page.getByRole("tooltip")).toContainText(/V [+−]\d\.\d\d · A [+−]\d\.\d\d/);
});

test("tag and octant filters narrow the map", async ({ page }) => {
  await page.goto("/");
  const filters = page.getByRole("group", { name: "Map filters" });
  await filters.getByRole("button", { name: "Excitement" }).click();
  const text = await page.getByText(/Showing \d+ of 40 tracks/).textContent();
  const shown = Number(text!.match(/Showing (\d+)/)![1]);
  expect(shown).toBeGreaterThan(0);
  expect(shown).toBeLessThan(40);
  await filters.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByText("Showing 40 of 40 tracks")).toBeVisible();
});

test("color by 2007 vs 2026 shows a legend", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel(/Color by/).selectOption("agreement");
  await expect(page.getByLabel("Legend: 2007 vs 2026 octant")).toBeVisible();
  await page.getByLabel(/Color by/).selectOption("tag:energetic");
  await expect(page.getByLabel(/Legend: “energetic” tag probability/)).toBeVisible();
});

test("clicking a point opens its track page", async ({ page }) => {
  await page.goto("/");
  await hoverAnyPoint(page);
  const title = await page.getByRole("tooltip").locator("strong").textContent();
  await page.mouse.down();
  await page.mouse.up();
  await expect(page.getByRole("heading", { name: title! })).toBeVisible();
  await expect(page.getByRole("img", { name: /Valence and arousal over/ })).toBeVisible();
  await expect(page.locator(".trajectory .series")).toHaveCount(2);
  await expect(page.getByLabel("2007 vs 2026")).toBeVisible();
  await expect(page.locator("audio")).toHaveAttribute("src", /data\/audio\/\d+\.wav$/); // demo stream
  await expect(page.getByLabel("Similar tracks").getByRole("link")).toHaveCount(10);
});

test("list sorts and links to tracks; deep links survive a reload", async ({ page }) => {
  await page.goto("/#/list");
  const header = page.getByRole("columnheader", { name: /^Arousal/ });
  await header.getByRole("button").click(); // "Arousal" is also an octant filter chip
  await expect(header).toHaveAttribute("aria-sort", "ascending");
  const first = page.getByRole("row").nth(1).getByRole("link");
  const title = await first.textContent();
  await first.click();
  await expect(page.getByRole("heading", { name: title! })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: title! })).toBeVisible();
});

test("lasso selection fills the side panel", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Full circumplex" }).click();
  const box = (await page.getByTestId("map-overlay").boundingBox())!;
  await page.keyboard.down("Shift");
  await page.mouse.move(box.x + box.width * 0.05, box.y + box.height * 0.05);
  await page.mouse.down();
  for (const [fx, fy] of [[0.95, 0.05], [0.95, 0.95], [0.05, 0.95], [0.05, 0.06]]) {
    await page.mouse.move(box.x + box.width * fx!, box.y + box.height * fy!, { steps: 6 });
  }
  await page.mouse.up();
  await page.keyboard.up("Shift");
  await expect(page.getByLabel("Selected tracks")).toContainText("40 selected");
  await page.keyboard.press("Escape");
  await expect(page.getByLabel("Selected tracks")).toHaveCount(0);
});

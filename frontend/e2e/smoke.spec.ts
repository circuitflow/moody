import { expect, test } from "@playwright/test";

/**
 * Data-agnostic checks, run in CI on the fixture and by the Pages workflow on the real demo
 * bundle before it is published.
 */
test.beforeEach(async ({ page }) => {
  page.on("pageerror", (err) => {
    throw err;
  });
});

test("smoke: map, a track page with credits, the path builder", async ({ page }) => {
  await page.goto("/");
  const count = page.getByText(/Showing \d[\d,]* of \d[\d,]* tracks/);
  await expect(count).toBeVisible();
  const total = Number((await count.textContent())!.match(/of ([\d,]+)/)![1]!.replace(/,/g, ""));
  expect(total).toBeGreaterThan(0);

  await page.getByRole("note").getByRole("link", { name: "Credits" }).click();
  await expect(page.getByRole("table").getByRole("row")).toHaveCount(total + 1);
  await page.getByRole("table").getByRole("row").nth(1).getByRole("link").first().click();
  await expect(page.locator(".attribution")).toContainText(/CC BY/);
  await expect(page.getByRole("img", { name: /Valence and arousal over/ })).toBeVisible();
  await expect(page.locator("audio")).toHaveAttribute("src", /.+/);

  await page.goto("/#/path");
  await expect(page.getByRole("complementary", { name: "Playlist" }).getByRole("listitem")).toHaveCount(
    Math.min(20, total),
  );
});

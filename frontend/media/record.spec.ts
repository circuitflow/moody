import { test, type Page } from "@playwright/test";

/** Each clip is saved as media/out/<name>.webm; media/to-gif.sh turns them into GIFs. */
function clip(name: string, body: (page: Page) => Promise<void>) {
  test(name, async ({ page }) => {
    await body(page);
    await page.waitForTimeout(600);
    const video = page.video();
    await page.close();
    await video?.saveAs(`media/out/${name}.webm`);
  });
}

async function glide(page: Page, from: [number, number], to: [number, number], steps = 30) {
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    await page.mouse.move(from[0] + (to[0] - from[0]) * t, from[1] + (to[1] - from[1]) * t);
    await page.waitForTimeout(25);
  }
}

clip("map", async (page) => {
  await page.goto("/");
  const overlay = page.getByTestId("map-overlay");
  await overlay.waitFor();
  await page.waitForTimeout(500);
  const b = (await overlay.boundingBox())!;
  // Wander across the map so tooltips come and go.
  await glide(page, [b.x + b.width * 0.15, b.y + b.height * 0.3], [b.x + b.width * 0.85, b.y + b.height * 0.35], 40);
  await glide(page, [b.x + b.width * 0.85, b.y + b.height * 0.35], [b.x + b.width * 0.4, b.y + b.height * 0.8], 40);
  await page.getByLabel(/Color by/).selectOption({ index: 1 });
  await page.waitForTimeout(1200);
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
  for (let i = 0; i < 6; i++) {
    await page.mouse.wheel(0, -120);
    await page.waitForTimeout(120);
  }
  await page.waitForTimeout(800);
});

clip("path", async (page) => {
  await page.goto("/#/path?n=15");
  const end = page.locator(".path-handle-end .path-handle-dot");
  await end.waitFor();
  await page.waitForTimeout(800);
  const e = (await end.boundingBox())!;
  const start: [number, number] = [e.x + e.width / 2, e.y + e.height / 2];
  await page.mouse.move(...start);
  await page.mouse.down();
  // Swing the end point up and around: the playlist re-plans as it moves.
  await glide(page, start, [start[0] - 120, start[1] - 260], 60);
  await glide(page, [start[0] - 120, start[1] - 260], [start[0] + 20, start[1] - 380], 40);
  await page.mouse.up();
  await page.waitForTimeout(700);
  await page.getByLabel(/Bend through a point/).check();
  await page.waitForTimeout(1200);
});

clip("track", async (page) => {
  await page.goto("/#/track/2");
  const chart = page.getByRole("img", { name: /Valence and arousal over/ });
  await chart.waitFor();
  await page.waitForTimeout(600);
  const c = (await chart.boundingBox())!;
  await glide(page, [c.x + 40, c.y + c.height / 2], [c.x + c.width - 80, c.y + c.height / 2], 50);
  await page.mouse.wheel(0, 500);
  await page.waitForTimeout(1200);
});

import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against the static build (the same build GitHub Pages serves), with a
 * deterministic fixture library from e2e/make_fixture.py (`npm run e2e:data`).
 */
export default defineConfig({
  testDir: "e2e",
  timeout: 30_000,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    launchOptions: process.env.PW_CHROMIUM_PATH
      ? { executablePath: process.env.PW_CHROMIUM_PATH }
      : {},
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1200, height: 950 } } }],
  webServer: {
    command: "npm run e2e:serve",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});

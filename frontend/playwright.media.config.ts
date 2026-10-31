import { defineConfig, devices } from "@playwright/test";

/**
 * Records the README clips (npm run media). Runs against the static build of whatever is in
 * public/data: the real demo bundle for the README, or the e2e fixture to try it out.
 */
export default defineConfig({
  testDir: "media",
  timeout: 60_000,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    ...devices["Desktop Chrome"],
    viewport: { width: 1200, height: 980 },
    video: { mode: "on", size: { width: 1200, height: 980 } },
    colorScheme: "light",
  },
  webServer: {
    command: "npm run e2e:serve",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});

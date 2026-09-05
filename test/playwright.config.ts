import { defineConfig, devices } from "@playwright/test";
import { BASE_URL, tourDismissed } from "./e2e/fixtures";

export default defineConfig({
  testDir: "./e2e",
  // Tests mutate one shared portfolio, so they run in order, not in parallel.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["html"], ["list"]] : [["list"]],
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: BASE_URL,
    storageState: tourDismissed,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});

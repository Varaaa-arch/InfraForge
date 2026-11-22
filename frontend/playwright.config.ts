import { defineConfig } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:5173";
const channel = process.env.PLAYWRIGHT_CHANNEL ?? "chrome";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 20_000 },
  reporter: [["list"]],
  outputDir: "test-results",
  use: {
    baseURL,
    channel,
    headless: process.env.PLAYWRIGHT_HEADED !== "1",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
});

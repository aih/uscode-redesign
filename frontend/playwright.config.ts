/**
 * The browser suite (`make test-e2e`).
 *
 * Separate from Vitest on purpose. Vitest covers `src/lib` — pure functions,
 * node environment, milliseconds — and its config deliberately excludes this
 * directory. What lives here is what only a browser can answer: hover timers,
 * the top layer, `position: sticky` geometry, `scroll-margin-top`, and whether
 * a media query gated the feature the way it was supposed to.
 *
 * It runs against a *running site* rather than starting one, because the site
 * is two processes behind a Caddy (ADR-0015) and reproducing that here would be
 * a second, lying copy of the deployment. `make dev-all` first.
 */
import { defineConfig, devices } from "@playwright/test";

const SITE = process.env.SITE ?? "http://localhost:8000";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  // A flaky assertion about hover timing is a bug in the assertion. Retries
  // would hide exactly the thing this suite exists to measure.
  retries: 0,
  reporter: process.env.CI ? "list" : "line",
  use: {
    baseURL: SITE,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 900 } },
    },
  ],
});

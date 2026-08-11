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
  // The accessibility scan (ADR-0039) spreads across worker processes, so each
  // scan writes a shard and these merge them into docs/verification/a11y.json.
  // Both are no-ops when no scan ran, which keeps them out of the way of every
  // other spec here. They live in `scripts/` because a global hook *inside*
  // testDir is loaded as part of the config, and every spec under that
  // directory is then loaded in the config's context — where `test.describe()`
  // throws and the suite collects as zero tests.
  globalSetup: "./scripts/a11y-setup.ts",
  globalTeardown: "./scripts/a11y-teardown.ts",
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
      // `shed.spec.ts` empties the `/app/diff/` token bucket on purpose. That
      // bucket is global and keyed on the client address (ADR-0029), and every
      // worker here shares one address — so beside it, any spec whose subject
      // is a redline gets a 429 instead of the thing it came to assert.
      testIgnore: "**/shed.spec.ts",
    },
    {
      name: "ratelimit",
      testMatch: "**/shed.spec.ts",
      // After everything else has finished, so the bucket it spends is nobody
      // else's, and serially, so it is not competing with itself either.
      dependencies: ["desktop"],
      fullyParallel: false,
      workers: 1,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 900 } },
    },
  ],
});

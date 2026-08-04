/**
 * Playwright `globalSetup` for the accessibility scan (ADR-0039).
 *
 * Wipes the shard directory. Without this, a run that scanned half the matrix
 * could inherit the other half from the previous run and look complete to the
 * merge in `a11y-teardown.ts`.
 *
 * This file lives in `scripts/` rather than next to the spec it serves, and it
 * has to: a `globalSetup` inside `testDir` is loaded as part of the *config*,
 * and every spec under that directory is then loaded in the config's context —
 * where `test.describe()` throws "did not expect test.describe() to be called
 * here" and the whole suite collects as zero tests.
 */
import { resetShards } from "../tests/e2e/a11y-report";

export default function globalSetup(): void {
  resetShards();
}

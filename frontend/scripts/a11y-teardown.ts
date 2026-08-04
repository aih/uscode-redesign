/**
 * Playwright `globalTeardown` for the accessibility scan (ADR-0039).
 *
 * Merges the per-scan shards into `docs/verification/a11y.json`. A no-op for a
 * run that scanned nothing, so the rest of the browser suite is unaffected.
 *
 * It lives in `scripts/` for the reason given in `a11y-setup.ts`.
 */
import { mergeShards } from "../tests/e2e/a11y-report";

export default function globalTeardown(): void {
  mergeShards();
}

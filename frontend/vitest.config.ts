import { defineConfig } from "vitest/config";

/**
 * Vitest over `src/lib` only — the renderer and the reference rules
 * (ADR-0015). The `.astro` pages themselves are exercised by `make shots`
 * (Playwright, against a running stack), not unit tests.
 */
export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    environment: "node",
  },
});

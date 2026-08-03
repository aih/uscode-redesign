/**
 * The ratchet that keeps the user guide honest (ADR-0038).
 *
 * `tests/e2e/guide.spec.ts` proves that what the guide *says* is true. Nothing
 * in it can notice what the guide fails to say — and an out-of-date guide is
 * far more often one that never mentioned a feature than one that describes it
 * wrongly. That is this file's job:
 *
 *   1. every chapter parses, and every scenario in it is well formed;
 *   2. every route the reader serves is claimed by some chapter;
 *   3. every ADR is either covered by a chapter or listed here as
 *      infrastructure, so a new decision has to be classified rather than
 *      quietly ignored;
 *   4. every demo scene is fully captioned and ordered.
 *
 * Rules 2 and 3 are what make "the guide is kept up to date" a property of the
 * build rather than a resolution. Adding a page to `src/pages/` or an ADR to
 * `docs/adr/` turns this red until the guide accounts for it. That is a real
 * tax on small changes and it is the intended one: the alternative, tried
 * everywhere and working nowhere, is remembering.
 *
 * It reads the filesystem rather than importing through Vite, deliberately — a
 * checker that asked the bundler for the file list could not report a file the
 * bundler never saw.
 */
import { readdirSync } from "node:fs";
import { basename, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

// @ts-expect-error - no type declarations for the shared .mjs extractor
import { readChapters, readScenarios } from "../scripts/scenarios.mjs";

const PAGES_DIR = fileURLToPath(new URL("../src/pages/", import.meta.url));
const ADR_DIR = fileURLToPath(new URL("../../docs/adr/", import.meta.url));

/**
 * Pages that are not features and so are not the guide's to document: the
 * error page, the health check, and the fragment endpoint the hover preview
 * fetches (which is machinery behind a feature `06-working-with-text` does
 * cover). The guide itself is excluded for the obvious reason.
 */
const UNDOCUMENTED_ROUTES = new Set(["/app/404", "/app/healthz", "/app/preview"]);

/** The guide does not document itself, chapter by chapter. */
function isGuidesOwnRoute(route: string): boolean {
  return route === "/app/guide" || route.startsWith("/app/guide/");
}

/**
 * ADRs with no reader-visible surface. Every one of these is a decision about
 * how the site is built rather than about what it does, and a user guide that
 * explained them would be a build log.
 *
 * Adding to this list is the escape hatch, and it is deliberately a diff: a
 * decision landing here rather than in a chapter should be a line someone
 * chose to write.
 */
const INFRASTRUCTURE_ADRS = new Set([
  1, // Postgres, sections as the storage atom
  2, // the schema-plural parser layer
  4, // USLM version detection by namespace
  5, // what counts as a section
  6, // the TOC comes from structural elements
  8, // per-release facts live on the release map
  11, // Astro/USWDS at /app
  12, // the resumable backfill
  14, // bulk-load resume state in the database
  15, // one origin, two services
  20, // deploy as one EC2 box
  22, // USWDS retained, no client framework
  30, // browser security headers
  35, // images from ECR, deploys from Actions
]);

const chapters = readChapters();
const scenarios = readScenarios();

/** Reader routes, derived from the files that serve them. A catch-all such as
 * `us/usc/[...identifier].astro` is claimed as its prefix, `/app/us/usc`,
 * because that is the address a chapter would name. */
function readerRoutes(): string[] {
  const routes: string[] = [];

  function walk(dir: string, prefix: string): void {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(path, `${prefix}/${entry.name}`);
        continue;
      }
      if (!/\.(astro|md|ts)$/.test(entry.name)) continue;

      const name = basename(entry.name).replace(/\.(astro|md|ts)$/, "");
      if (name.startsWith("[")) {
        routes.push(prefix);
      } else if (name === "index") {
        routes.push(prefix === "/app" ? "/app/" : prefix);
      } else {
        routes.push(`${prefix}/${name}`);
      }
    }
  }

  walk(PAGES_DIR, "/app");
  return [...new Set(routes)];
}

function adrNumbers(): number[] {
  return readdirSync(ADR_DIR)
    .filter((name) => /^\d{4}-.*\.md$/.test(name))
    .map((name) => Number(name.slice(0, 4)));
}

describe("the guide's chapters", () => {
  it("all parse, with frontmatter and scenarios", () => {
    // `readChapters()` throws on a malformed chapter; reaching here means every
    // one of them is readable. The assertion is that there are chapters at all,
    // so an empty directory cannot pass this file silently.
    expect(chapters.length).toBeGreaterThan(0);
    for (const chapter of chapters) {
      expect(chapter.frontmatter.title, `${chapter.file} needs a title`).toBeTruthy();
      expect(chapter.frontmatter.layout, `${chapter.file} needs a layout`).toContain(
        "GuideLayout.astro",
      );
    }
  });

  it("are ordered without ties", () => {
    const orders = chapters.map((c) => c.frontmatter.order);
    expect(new Set(orders).size, `chapter order values collide: ${orders.join(", ")}`).toBe(
      orders.length,
    );
  });
});

describe("what the guide covers", () => {
  it("documents every route the reader serves", () => {
    const claimed = new Set<string>(
      chapters.flatMap((chapter) => chapter.frontmatter.covers.routes),
    );

    const undocumented = readerRoutes()
      .filter((route) => !UNDOCUMENTED_ROUTES.has(route))
      .filter((route) => !isGuidesOwnRoute(route))
      .filter((route) => !claimed.has(route));

    expect(
      undocumented,
      `these reader routes are in no chapter's covers.routes — document them in a guide chapter, ` +
        `or add them to UNDOCUMENTED_ROUTES here if they are not features`,
    ).toEqual([]);
  });

  it("accounts for every ADR, as a chapter or as infrastructure", () => {
    const claimed = new Set<number>(chapters.flatMap((chapter) => chapter.frontmatter.covers.adrs));

    const unclassified = adrNumbers().filter(
      (adr) => !claimed.has(adr) && !INFRASTRUCTURE_ADRS.has(adr),
    );

    expect(
      unclassified,
      `these ADRs are neither covered by a guide chapter nor listed as infrastructure — ` +
        `if the decision changed what a reader sees, say so in a chapter; if it did not, ` +
        `add it to INFRASTRUCTURE_ADRS with a one-line reason`,
    ).toEqual([]);
  });

  it("claims no route that does not exist", () => {
    // The other direction: a chapter covering a page that has since been
    // deleted is a chapter documenting something nobody can visit. The bare
    // citation URL is served by FastAPI rather than by a page file, so it is
    // named here as the one legitimate exception.
    const served = new Set([...readerRoutes(), "/us/usc"]);
    const phantom = chapters
      .flatMap((chapter) => chapter.frontmatter.covers.routes.map((r: string) => [chapter.file, r]))
      .filter(([, route]) => !served.has(route));

    expect(phantom, "a chapter covers a route the site does not serve").toEqual([]);
  });
});

describe("the demo scenes", () => {
  const demo = scenarios.filter((s: any) => s.demo);

  it("exist", () => {
    expect(demo.length, "no scenario is flagged demo: true, so the video has nothing to record")
      .toBeGreaterThan(0);
  });

  it("are captioned at every step", () => {
    // `readScenarios()` enforces this too; asserting it here is what makes the
    // failure legible in `make test-web` rather than only in the video script.
    for (const scenario of demo) {
      for (const [index, step] of scenario.steps.entries()) {
        expect(step.caption, `${scenario.id} step ${index + 1} has no caption`).toBeTruthy();
      }
    }
  });

  it("have a total running time a viewer would sit through", () => {
    // The captions are the narration, and they are paced by their own length
    // in `demovideo.mjs`. This is the same arithmetic, kept here so the guide
    // cannot grow into a twenty-minute video without anyone noticing.
    const seconds = demo.reduce(
      (total: number, scenario: any) =>
        total +
        scenario.steps.reduce(
          (sum: number, step: any) => sum + Math.max(2.5, (step.caption?.length ?? 0) * 0.06),
          0,
        ),
      0,
    );
    expect(seconds, `the demo would run ${Math.round(seconds)}s`).toBeLessThan(360);
  });
});

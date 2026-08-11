/**
 * Headless screenshots of the reader at the two widths the BUILDLOG 008 review
 * asked about: a 375px phone and a 1280px desktop.
 *
 * Evidence, not decoration. "Mobile-first" is the kind of claim that is easy to
 * make and easy to be wrong about, and a committed PNG is checkable by anyone
 * who reads the repository later.
 *
 *   npm run shots                     # against http://localhost:8000 (make dev-all)
 *   SITE=http://localhost:4321 npm run shots
 */

import { mkdir, readFile } from "node:fs/promises";
import { chromium } from "playwright";

const SITE = process.env.SITE ?? "http://localhost:8000";
const OUT = new URL("../../docs/screenshots/", import.meta.url);

const PAGES = [
  // The demo URL scrolls to its highlighted provision, which is the point of it
  // — so the plain section is shot too, for the title bar and the top nav strip.
  ["demo", "/app/us/usc/t16/s45f/c/5?date=07/12/2026"],
  ["section", "/app/us/usc/t16/s45f"],
  ["toc", "/app/us/usc/t16/ch1"],
  ["home", "/app/"],
  // Session 14's pages. `docs` earns its place in this list rather than only in
  // the gallery: it renders a parameter *table* per endpoint, and a table is
  // the thing most likely to push a phone sideways — which is exactly what the
  // overflow assertion below catches.
  ["search", "/app/search?q=conservation"],
  ["syntax", "/app/search/syntax"],
  ["docs", "/app/docs"],
  // Session 15: the page the footer disclaimer now leads to.
  ["about", "/app/about"],
  // Session 22: the user guide (ADR-0038). A chapter is the widest prose on the
  // site and its scenario boxes hold long identifiers, so it is exactly the
  // shape the overflow assertion below exists to catch.
  ["guide", "/app/guide"],
  ["guide-chapter", "/app/guide/02-reading"],
  // A `<video>` is a replaced element with intrinsic dimensions — 1280px of
  // them — so it is one of the few things on this site that will push a phone
  // sideways if its CSS is wrong, which is precisely what the assertion below
  // is for.
  ["demo-video", "/app/demo"],
  // Session 30: the design system (ADR-0053). Every component the reader has,
  // on one page, which makes it the one shot where a token change is visible
  // without knowing which route to open — and a table of colour pairs, which is
  // the other shape that pushes a phone sideways.
  ["design", "/app/design"],
  // Session 48: a classification table (ADR-0067). Five columns of fixed-width
  // source data — the widest table on the site, and the one most likely to push
  // a phone sideways, which is what the overflow assertion below is for.
  ["classification", "/app/classification/118/2"],
];

/**
 * Each entry is a label, a viewport, and a page zoom.
 *
 * The last two rows are the mechanical half of WCAG 1.4.10 Reflow and 1.4.4
 * Resize text (ADR-0039). Both are about how many CSS pixels the layout has to
 * work with, and zoom is how a reader takes them away: doubling the zoom halves
 * them. So 1280 at 200% lays out in 640, which is 1.4.4's requirement, and 320
 * at no zoom is 1.4.10's floor — the same width 1280 reaches at 400%.
 *
 * 320 at 200% would lay out in 160, and is not here. WCAG 2.1 AA asks for
 * reflow down to 320 CSS pixels and no further, so an assertion at 160 would
 * fail this build on something the standard does not require. Measured: the
 * demo URL scrolls sideways by 86px there.
 *
 * The zoom is the CSS `zoom` property on the root element, the closest
 * scriptable analogue to the browser's own zoom control — it reflows, where
 * `deviceScaleFactor` only resamples.
 */
const WIDTHS = [
  ["375", { width: 375, height: 812 }, 1],
  ["1280", { width: 1280, height: 900 }, 1],
  ["320", { width: 320, height: 768 }, 1],
  ["1280-zoom200", { width: 1280, height: 900 }, 2],
];

await mkdir(OUT, { recursive: true });

/**
 * Reflow failures that are known, owned and not yet fixed — the same ratchet
 * `a11y.spec.ts` runs on axe's findings, applied to the overflow assertion
 * below, and read from the same file so there is one list to empty (ADR-0039).
 *
 * A listed (page, view) pair is reported and allowed through. Anything else
 * throws. A pair that has stopped overflowing is reported at the end, because
 * an exception nobody removed is how a fixed bug goes on looking like a bug.
 */
const KNOWN_REFLOW = JSON.parse(
  await readFile(new URL("../../docs/a11y/known-violations.json", import.meta.url), "utf8"),
).reflow;

const knownReflow = (name, view) =>
  KNOWN_REFLOW.find((entry) => entry.page === name && entry.view === view);

const failures = [];
const unusedReflow = new Set(KNOWN_REFLOW.map((e) => `${e.page} ${e.view}`));

const browser = await chromium.launch();
try {
  for (const [width, viewport, zoom] of WIDTHS) {
    const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
    // Before any document script, so the page lays out zoomed from the first
    // paint rather than reflowing once under the measurement.
    if (zoom !== 1) {
      await context.addInitScript((factor) => {
        document.addEventListener("DOMContentLoaded", () => {
          document.documentElement.style.zoom = String(factor);
        });
      }, zoom);
    }
    const page = await context.newPage();
    for (const [name, path] of PAGES) {
      // `load`, not `networkidle`. Since the Day-5 islands landed, the reader
      // never goes network-idle on its own — `WatchButton` fires `/auth/me`
      // after paint and the citation preview keeps a listener alive — so
      // `networkidle` waited out its 30 s timeout on every page and `make shots`
      // had silently stopped working. The islands are not what these images are
      // of; the server-rendered page is, and that is complete at `load`.
      const response = await page.goto(`${SITE}${path}`, { waitUntil: "load" });
      if (!response?.ok()) {
        throw new Error(`${path} answered ${response?.status()}`);
      }
      const view = width;
      // Give the one deferred thing that *does* change the picture — the watch
      // widget resolving to a single button — a moment to settle.
      await page.waitForTimeout(500);
      // The page must not scroll sideways at any width — the one failure mode a
      // full-page screenshot would otherwise hide.
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      if (overflow > 0) {
        const known = knownReflow(name, view);
        const where =
          `${path} at ${view} scrolls horizontally by ${overflow}px` +
          (zoom !== 1 ? ` (${viewport.width}px at ${zoom * 100}% zoom)` : "");
        if (known) {
          unusedReflow.delete(`${name} ${view}`);
          console.log(`  known reflow (${known.owner}): ${where}`);
        } else {
          failures.push(
            `${where} — not in docs/a11y/known-violations.json. Fix it, or add a ` +
              `"reflow" entry for page "${name}" at view "${view}" with an owner task.`,
          );
        }
      } else {
        unusedReflow.delete(`${name} ${view}`);
      }
      // Viewport-sized, not full-page: a chapter TOC is 10,000px tall, and a
      // 1.5 MB PNG of it proves nothing that the first screenful does not.
      await page.screenshot({ path: new URL(`${name}-${width}.png`, OUT).pathname });
      console.log(`${name}-${width}.png`);
    }
    await context.close();
  }
} finally {
  await browser.close();
}

for (const stale of unusedReflow) {
  failures.push(
    `docs/a11y/known-violations.json lists a reflow exception for "${stale}" that no longer ` +
      `overflows. Remove it.`,
  );
}

if (failures.length > 0) {
  throw new Error(`\n  ${failures.join("\n  ")}\n`);
}

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

import { mkdir } from "node:fs/promises";
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
];

const WIDTHS = [
  ["375", { width: 375, height: 812 }],
  ["1280", { width: 1280, height: 900 }],
];

await mkdir(OUT, { recursive: true });

const browser = await chromium.launch();
try {
  for (const [width, viewport] of WIDTHS) {
    const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
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
      // Give the one deferred thing that *does* change the picture — the watch
      // widget resolving to a single button — a moment to settle.
      await page.waitForTimeout(500);
      // The page must not scroll sideways at any width — the one failure mode a
      // full-page screenshot would otherwise hide.
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      if (overflow > 0) {
        throw new Error(`${path} at ${width}px scrolls horizontally by ${overflow}px`);
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

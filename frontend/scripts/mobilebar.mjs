/**
 * What the header costs below the desktop breakpoint, and whether the search
 * box is reachable without opening anything.
 *
 * ADR-0058 put the nav behind a hamburger, ADR-0061 put five more links behind
 * More, and each of those was argued from a measurement of the header's height.
 * B9 rearranges the same widths again — a 52px bar and a search row under it —
 * so the same numbers are taken the same way rather than described.
 *
 *   node scripts/mobilebar.mjs                     # against http://localhost:8000
 *   SITE=http://localhost:4321 node scripts/mobilebar.mjs
 *
 * Four things per width, all with the menu **closed**, which is the state a
 * reader arrives in:
 *
 *   headerPx      the whole `<header>`, which is what the chrome costs before
 *                 the reader has done anything
 *   barPx         the top row alone: below 64em the Menu / wordmark / theme
 *                 bar, above it the whole nav row
 *   searchVisible whether the one search box (ADR-0023) is on screen without
 *                 opening a menu
 *   smallestTargetPx  the shortest side of the smallest hit target on the bar,
 *                 which the mobile spec holds at 44
 *
 * Then the sticky stack, scrolled, at the widths where the header pins
 * (40em and up) — that is what `--sticky-h` has to cover and what every anchor
 * jump spends.
 *
 * Writes docs/verification/mobilebar.json. To reproduce a before column, run it
 * against a tree at the commit before the change.
 */
import { mkdir, writeFile } from "node:fs/promises";
import { chromium } from "playwright";

const SITE = process.env.SITE ?? "http://localhost:8000";
const OUT = new URL("../../docs/verification/", import.meta.url);

/** `/us/usc/t16/s470a` carries the deepest breadcrumb to hand, so it is the
 * worst case for the sticky stack; `s45f` is what every other chrome
 * measurement in this repo uses. Both, because the header is the same on each
 * and the stack is not. */
const PAGE = `${SITE}/app/us/usc/t16/s45f`;
const DEEP = `${SITE}/app/us/usc/t16/s470a`;

/** 320 and 375 are phones; 420 is where the footer's columns split; 640 is the
 * narrowest width at which the header sticks and 1023 the widest below the
 * desktop breakpoint; 1280 is the desktop check that nothing here moved it. */
const WIDTHS = [320, 375, 420, 640, 700, 1023, 1280];

/** Where the header sticks, so the stack is worth measuring. Below 40em only
 * the section bar pins (`site.scss`). */
const STICKY_FROM = 640;

const browser = await chromium.launch();
const header = [];
const sticky = [];

for (const width of WIDTHS) {
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  // Generous, because this also has to run against `npm run dev`, where the
  // first request compiles the stylesheet.
  await page.goto(PAGE, { waitUntil: "load", timeout: 60_000 });

  const measured = await page.evaluate(() => {
    const round = (n) => Math.round(n * 100) / 100;
    const box = (sel) => {
      const el = document.querySelector(sel);
      return el ? round(el.getBoundingClientRect().height) : null;
    };

    // The bar is `.navbar` below 64em and the whole nav row above it, where
    // that element is `display: contents` and has no box of its own.
    const bar = document.querySelector(".navbar");
    const barPx =
      bar && getComputedStyle(bar).display !== "contents"
        ? round(bar.getBoundingClientRect().height)
        : box(".usa-nav");

    const input = document.querySelector(".navtools .sitesearch__input");
    const rect = input?.getBoundingClientRect();
    const searchVisible = Boolean(
      rect && rect.width > 0 && rect.height > 0 && rect.top < window.innerHeight,
    );

    // Every focusable thing on the top row, whichever row that is. The search
    // box is excluded: it is its own row below 64em, and its "i" is an 18px
    // glyph whose hit area is grown past 44px with `::after`, which a bounding
    // box cannot see and `chrome.spec.ts` asserts by clicking outside it.
    const row = bar ?? document.querySelector(".usa-nav");
    const targets = [...row.querySelectorAll("summary, a, button")]
      .filter((el) => !el.closest(".navtools"))
      .filter((el) => el.offsetParent !== null || getComputedStyle(el).position === "fixed")
      .map((el) => {
        const r = el.getBoundingClientRect();
        return { name: el.className || el.tagName, px: round(Math.min(r.width, r.height)) };
      })
      .filter((t) => t.px > 0);

    return {
      headerPx: box("header.usa-header"),
      barPx,
      searchVisible,
      searchInputPx: rect ? round(rect.width) : null,
      smallestTargetPx: targets.length ? Math.min(...targets.map((t) => t.px)) : null,
      targets,
    };
  });

  header.push({ viewport: width, ...measured });
  await page.close();
}

for (const width of WIDTHS.filter((w) => w >= STICKY_FROM)) {
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  await page.goto(DEEP, { waitUntil: "load", timeout: 60_000 });
  // Unscrolled, a sticky element sits at its natural place and reports a height
  // that means nothing. Scroll first, then measure.
  await page.evaluate(() => window.scrollTo(0, 1200));
  await page.waitForTimeout(200);

  const stackPx = await page.evaluate(() => {
    let bottom = 0;
    for (const el of document.querySelectorAll("body *")) {
      if (getComputedStyle(el).position !== "sticky") continue;
      // The chapter rail is sticky too (ADR-0050) and is not chrome: it pins
      // *below* the stack, at `--sticky-h`, so counting it would make this
      // number a function of itself. `--sticky-h` is what the stack above
      // `<main>` costs.
      if (el.closest("main")) continue;
      const r = el.getBoundingClientRect();
      if (r.height > 0 && r.bottom > bottom) bottom = r.bottom;
    }
    return Math.round(bottom * 100) / 100;
  });

  sticky.push({ viewport: width, stackPx });
  await page.close();
}

await browser.close();

await mkdir(OUT, { recursive: true });
await writeFile(
  new URL("mobilebar.json", OUT),
  `${JSON.stringify(
    {
      _comment:
        "The header's cost below the desktop breakpoint, menu closed, and the sticky " +
        "stack it feeds. Regenerate with `make mobilebar` against a running site (ADR-0064).",
      headerPage: "/app/us/usc/t16/s45f",
      stickyPage: "/app/us/usc/t16/s470a",
      header,
      sticky,
    },
    null,
    2,
  )}\n`,
);

console.log("  width  header    bar   search  smallest target");
for (const r of header) {
  console.log(
    `${String(r.viewport).padStart(7)} ${String(r.headerPx).padStart(7)}px ` +
      `${String(r.barPx).padStart(6)}px  ${r.searchVisible ? "shown " : "hidden"}  ` +
      `${String(r.smallestTargetPx).padStart(6)}px`,
  );
}
console.log("\n  sticky stack, scrolled");
for (const r of sticky) {
  console.log(`${String(r.viewport).padStart(7)} ${String(r.stackPx).padStart(7)}px`);
}

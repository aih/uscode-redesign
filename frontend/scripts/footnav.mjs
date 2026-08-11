/**
 * How much of a screen the footer's own links take, once opened.
 *
 * ADR-0058 collapsed the nine of them behind a disclosure because they were
 * 326px of menu at 375px; ADR-0062 grouped them under four headings, which
 * buys columns at most widths and costs a label row at the narrowest. That
 * trade is a number, so it is measured rather than described.
 *
 *   node scripts/footnav.mjs                    # against http://localhost:8000
 *   SITE=http://localhost:4321 node scripts/footnav.mjs
 *
 * The disclosure is opened where it exists, since a reader who wants the links
 * has opened it — the closed state is one 44px summary at every width and says
 * nothing about the layout underneath. Writes docs/verification/footnav.json.
 *
 * To reproduce the before column of ADR-0062's table, run it against a tree at
 * f5d49a0, the commit before the grouping.
 */
import { mkdir, writeFile } from "node:fs/promises";
import { chromium } from "playwright";

const SITE = process.env.SITE ?? "http://localhost:8000";
const OUT = new URL("../../docs/verification/", import.meta.url);
const PAGE = `${SITE}/app/us/usc/t16/s45f`;

/** 320 and 375 are one column, 420 two, 640 and 700 four behind the disclosure,
 * 1280 four in the open. The `make shots` widths, plus the two breakpoints. */
const WIDTHS = [320, 375, 420, 640, 700, 1280];

const browser = await chromium.launch();
const results = [];

for (const width of WIDTHS) {
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  // Generous, because this also has to run against `npm run dev`, where the
  // first request compiles the stylesheet.
  await page.goto(PAGE, { waitUntil: "load", timeout: 60_000 });

  const summary = page.locator(".footmenu__summary");
  const collapsed = await summary.isVisible();
  if (collapsed) await summary.click();

  const box = await page.locator(".usa-footer__nav").boundingBox();
  const columns = await page
    .locator(".footnav")
    .evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(" ").length);

  results.push({
    viewport: width,
    collapsedBehindDisclosure: collapsed,
    navHeightPx: Math.round(box.height),
    columns,
  });
  await page.close();
}

await browser.close();

await mkdir(OUT, { recursive: true });
await writeFile(
  new URL("footnav.json", OUT),
  `${JSON.stringify(
    {
      _comment:
        "Height of the footer's link block, disclosure open, per viewport width. " +
        "Regenerate with `make footnav` against a running site (ADR-0062).",
      page: "/app/us/usc/t16/s45f",
      results,
    },
    null,
    2,
  )}\n`,
);

for (const r of results) {
  console.log(
    `${String(r.viewport).padStart(4)}px  ${String(r.navHeightPx).padStart(4)}px  ` +
      `${r.columns} column${r.columns === 1 ? "" : "s"}` +
      (r.collapsedBehindDisclosure ? "  (behind the disclosure)" : ""),
  );
}

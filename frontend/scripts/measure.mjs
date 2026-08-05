/**
 * How many characters a line of statutory text actually holds.
 *
 * The reading measure is a brand decision (ADR-0052) and it is stated as a
 * width — `--measure` — while the thing it is meant to control is a character
 * count. Those two are related only through the face and the size, so a face
 * change moves the count without moving the token, and the token is either
 * still 62–70 characters or it quietly stopped being.
 *
 *   node scripts/measure.mjs                    # against http://localhost:8000
 *   SITE=http://localhost:4321 node scripts/measure.mjs
 *
 * Counts where the browser broke the lines rather than dividing the column
 * width by an average glyph, so the number is the text the reader is looking at.
 * Writes docs/verification/measure.json.
 */
import { mkdir, writeFile } from "node:fs/promises";
import { chromium } from "playwright";

const SITE = process.env.SITE ?? "http://localhost:8000";
const OUT = new URL("../../docs/verification/", import.meta.url);

/** Widths that put the reading column at, below and well above its maximum. */
const WIDTHS = [375, 768, 1280];

/** A long, ordinary provision — prose rather than a list of short paragraphs. */
const PAGE = "/app/us/usc/t16/s45f";

/**
 * Line lengths of every paragraph of statutory text on the page.
 *
 * Each character is measured on its own — a one-character Range, its rectangle
 * bucketed by vertical midpoint — and the characters sharing a bucket are one
 * rendered line. Slower than bisecting for the line breaks, and correct where
 * bisection is not: a footnote marker or a `<sup>` inside a provision is a
 * shorter box on the same line, so "the y position increases with the offset"
 * is not true of this text.
 *
 * The last line of a paragraph is dropped. It ends where the sentence ends
 * rather than where the column does, and counting it reports a measure narrower
 * than the one on screen.
 */
async function lineLengths(page) {
  return page.evaluate(() => {
    const lengths = [];
    const nodes = document.querySelectorAll(".section-body p, .section-body .prov__text");
    for (const node of nodes) {
      const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
      const runs = [];
      let current;
      while ((current = walker.nextNode())) runs.push(current);
      if (runs.length === 0) continue;
      if (runs.reduce((sum, r) => sum + r.length, 0) < 120) continue;

      const buckets = new Map();
      const probe = document.createRange();
      for (const run of runs) {
        for (let i = 0; i < run.length; i += 1) {
          probe.setStart(run, i);
          probe.setEnd(run, i + 1);
          const rect = probe.getBoundingClientRect();
          if (rect.width === 0 && rect.height === 0) continue;
          // 4px buckets: enough to separate two lines, coarse enough that a
          // superscript on the same line does not become a line of its own.
          const line = Math.round((rect.top + rect.height / 2) / 4);
          buckets.set(line, (buckets.get(line) ?? 0) + 1);
        }
      }
      const lines = [...buckets.entries()].sort((a, b) => a[0] - b[0]).map(([, n]) => n);
      if (lines.length < 2) continue;
      lengths.push(...lines.slice(0, -1));
    }
    return lengths;
  });
}

function summarise(lengths) {
  const sorted = [...lengths].sort((a, b) => a - b);
  const at = (q) => sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))];
  return {
    lines: sorted.length,
    min: sorted[0] ?? null,
    p10: at(0.1) ?? null,
    median: at(0.5) ?? null,
    p90: at(0.9) ?? null,
    max: sorted[sorted.length - 1] ?? null,
    mean: sorted.length ? Number((sorted.reduce((a, b) => a + b, 0) / sorted.length).toFixed(1)) : null,
  };
}

/**
 * Sections to record the scroll length of.
 *
 * A narrower measure is more lines, and more lines is a longer page — which is
 * the cost ADR-0052 accepts and therefore the number it has to be able to show.
 * Three lengths of section: short, long, and one carrying a table.
 */
const HEIGHTS = ["/app/us/usc/t16/s45f", "/app/us/usc/t16/s470a", "/app/us/usc/t16/s1801"];

const browser = await chromium.launch();
const results = [];
const heights = [];

for (const path of HEIGHTS) {
  for (const width of [375, 1280]) {
    const context = await browser.newContext({ viewport: { width, height: 900 } });
    const page = await context.newPage();
    await page.goto(`${SITE}${path}`, { waitUntil: "networkidle" });
    await page.evaluate(() => document.fonts.ready);
    heights.push({
      page: path,
      viewport: width,
      scrollHeightPx: await page.evaluate(() => document.documentElement.scrollHeight),
    });
    await context.close();
  }
}

for (const width of WIDTHS) {
  const context = await browser.newContext({ viewport: { width, height: 900 } });
  const page = await context.newPage();
  await page.goto(`${SITE}${PAGE}`, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);

  const columnWidth = await page.evaluate(() => {
    const body = document.querySelector(".section-body");
    return body ? Math.round(body.getBoundingClientRect().width) : null;
  });
  const family = await page.evaluate(() => {
    const el = document.querySelector(".section-body");
    return el ? getComputedStyle(el).fontFamily : null;
  });
  const size = await page.evaluate(() => {
    const el = document.querySelector(".section-body");
    return el ? getComputedStyle(el).fontSize : null;
  });

  results.push({
    viewport: width,
    page: PAGE,
    columnWidthPx: columnWidth,
    fontFamily: family,
    fontSize: size,
    characters: summarise(await lineLengths(page)),
  });
  await context.close();
}

await browser.close();
await mkdir(OUT, { recursive: true });
await writeFile(
  new URL("measure.json", OUT),
  `${JSON.stringify(
    {
      _comment:
        "Generated by frontend/scripts/measure.mjs against a running site. Do not hand-edit " +
        "— re-run it. Characters per rendered line of statutory text, counted from " +
        "Range.getClientRects() rather than estimated from a glyph width. Final lines of a " +
        "paragraph are excluded: they end where the sentence ends, not where the column does. " +
        "ADR-0052 holds the median between 62 and 70 at the widths where the column is at its " +
        "maximum. documentHeights is the scroll length of three sections at two widths, which " +
        "is what a narrower measure costs.",
      site: SITE,
      results,
      documentHeights: heights,
    },
    null,
    2,
  )}\n`,
);

for (const result of results) {
  const c = result.characters;
  console.log(
    `${String(result.viewport).padStart(4)}px  column ${String(result.columnWidthPx).padStart(4)}px  ` +
      `${c.lines} lines  median ${c.median}  p10-p90 ${c.p10}-${c.p90}`,
  );
}

/**
 * Measuring where the browser actually broke a line of statutory text.
 *
 * Shared by `scripts/measure.mjs`, which records it, and
 * `tests/e2e/typography.spec.ts`, which gates on it. The two halves of
 * `make measure` were split because only one of them is a check: the
 * character count is a claim ADR-0052 makes about every page, and it was
 * being verified by a target nothing ran. The scroll lengths beside it are a
 * record, and stay in the target.
 *
 * The band and the widths live here so the gate and the record cannot drift
 * apart while both look right.
 */

/** The band ADR-0052 holds the median in. Only checked where the column is at
 * its maximum: below that the viewport is the measure and 38 characters is the
 * screen's fault, not the token's. */
export const BAND = { low: 62, high: 70 };

/** The width at and above which the column stops being viewport-bound. */
export const FULL_WIDTH = 768;

/** Widths that put the reading column at, below and well above its maximum. */
export const WIDTHS = [375, 768, 1280];

/** The two settings of the reading-density control (ADR-0054). `null` is the
 * default — no attribute on `<html>` at all, which is what a reader who has
 * never touched the control gets. */
export const DENSITIES = [null, "compact"];

/** A long, ordinary provision — prose rather than a list of short paragraphs. */
export const PAGE = "/app/us/usc/t16/s45f";

/** Stamp the density on `<html>` before the page's own scripts run, the way the
 * pre-paint bootstrap in `Base.astro` does — so the page is laid out at this
 * density from the first paint and nothing here is measuring a reflow. */
export async function withDensity(context, density) {
  await context.addInitScript((value) => {
    try {
      if (value) localStorage.setItem("usc-density", value);
      else localStorage.removeItem("usc-density");
    } catch {
      // No storage in this context; the default stands and the run says so.
    }
  }, density);
}

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
export async function lineLengths(page) {
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

export function summarise(lengths) {
  const sorted = [...lengths].sort((a, b) => a - b);
  const at = (q) => sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))];
  return {
    lines: sorted.length,
    min: sorted[0] ?? null,
    p10: at(0.1) ?? null,
    median: at(0.5) ?? null,
    p90: at(0.9) ?? null,
    max: sorted[sorted.length - 1] ?? null,
    mean: sorted.length
      ? Number((sorted.reduce((a, b) => a + b, 0) / sorted.length).toFixed(1))
      : null,
  };
}

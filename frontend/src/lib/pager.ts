/**
 * What a pager has to work out before it can draw itself (ADR-0071).
 *
 * A module rather than a block of frontmatter inside `Pager.astro` for one
 * reason: this is arithmetic with edges — an offset that is not a multiple of
 * the page size, an offset past the end, a total of zero, a last page with one
 * row on it — and arithmetic with edges is worth testing without a browser and
 * without a corpus. `tests/pager.test.ts` covers the cases; the component
 * renders what comes back and decides nothing itself.
 */

export interface PagerModel {
  /** How many pages the total makes at this page size. Never below 1. */
  pages: number;
  /** The page this offset lands on, 1-based. */
  current: number;
  /** The first and last row this page shows, 1-based and inclusive. Both 0
   *  when the page is empty — an offset past the end, or nothing matched. */
  from: number;
  to: number;
  /**
   * The page numbers to draw, `null` where the sequence skips.
   *
   * The first page, the last page, and a window either side of the current one.
   * A gap is a `null` rather than an ellipsis so the rendering stays a decision
   * of the component's, and so a caller counting pages does not have to know
   * which strings are not numbers.
   */
  numbers: (number | null)[];
  /** Are there pages the numbers do not reach? What decides whether a jump box
   *  is worth its space. */
  truncated: boolean;
}

export interface PagerInput {
  /** Rows the filters matched — not rows on this page. */
  total: number;
  /** The row this page starts at. */
  offset: number;
  /** Rows to a page. */
  limit: number;
  /** Rows actually returned, which is what the range can honestly claim. */
  shown: number;
  /** Pages either side of the current one. 2 gives at most 7 numbers. */
  window?: number;
}

export function pagerModel({
  total,
  offset,
  limit,
  shown,
  window = 2,
}: PagerInput): PagerModel {
  const size = Math.max(1, Math.floor(limit));
  const rows = Math.max(0, Math.floor(total));
  const start = Math.max(0, Math.floor(offset));
  const pages = Math.max(1, Math.ceil(rows / size));
  // The page an offset *lands on*, not the page it starts: `?offset=75` at 50
  // to a page is inside page 2, and the controls have to agree with the rows on
  // screen rather than with the arithmetic that would have produced them.
  const current = Math.min(pages, Math.floor(start / size) + 1);

  const numbers: (number | null)[] = [];
  let previous = 0;
  for (let page = 1; page <= pages; page += 1) {
    const near = Math.abs(page - current) <= window;
    if (page !== 1 && page !== pages && !near) continue;
    if (previous && page - previous > 1) numbers.push(null);
    numbers.push(page);
    previous = page;
  }

  return {
    pages,
    current,
    from: shown > 0 ? start + 1 : 0,
    to: shown > 0 ? start + shown : 0,
    numbers,
    truncated: numbers.includes(null),
  };
}

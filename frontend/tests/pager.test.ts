/**
 * The pager's arithmetic (ADR-0071).
 *
 * Everything here is an edge the CI fixture corpus cannot reach: its largest
 * classification table is 84 rows, which is two pages, and two pages exercise
 * neither the window nor the gap nor the jump box. The numbers below are the
 * real corpus's — the 104th's 11,737 rows at 50 to a page — so the control is
 * tested against the sizes it was built for rather than against the sizes the
 * test data happens to have.
 */
import { describe, expect, it } from "vitest";

import { pagerModel } from "../src/lib/pager";
import { pageOffset } from "../src/lib/url";

const page = (over: Partial<Parameters<typeof pagerModel>[0]> = {}) =>
  pagerModel({ total: 11_737, offset: 0, limit: 50, shown: 50, ...over });

describe("pagerModel", () => {
  it("counts the pages a total makes and says which one this is", () => {
    expect(page().pages).toBe(235);
    expect(page().current).toBe(1);
    expect(page({ offset: 5_000 }).current).toBe(101);
    // The last page is short, and a short page is still a page.
    expect(page({ offset: 11_700, shown: 37 }).current).toBe(235);
    expect(page({ offset: 11_700, shown: 37 }).to).toBe(11_737);
  });

  it("puts an offset that starts no page on the page it lands in", () => {
    // ?offset=75 at 50 to a page shows rows 76–125, which is inside page 2.
    const model = page({ offset: 75 });
    expect(model.current).toBe(2);
    expect(model.from).toBe(76);
  });

  it("keeps the two ends reachable and marks the gaps between", () => {
    expect(page({ offset: 5_000 }).numbers).toEqual([
      1,
      null,
      99,
      100,
      101,
      102,
      103,
      null,
      235,
    ]);
    // Near an end there is only one gap, and no gap is drawn for a single
    // page skipped — `1 … 3` says nothing `1 2 3` does not.
    expect(page().numbers).toEqual([1, 2, 3, null, 235]);
    expect(page({ offset: 100 }).numbers).toEqual([1, 2, 3, 4, 5, null, 235]);
    expect(page({ offset: 150 }).numbers).toEqual([1, 2, 3, 4, 5, 6, null, 235]);
  });

  it("draws every page when they all fit, and offers no jump box", () => {
    const short = pagerModel({ total: 84, offset: 0, limit: 50, shown: 50 });
    expect(short.pages).toBe(2);
    expect(short.numbers).toEqual([1, 2]);
    expect(short.truncated).toBe(false);
    expect(page({ offset: 5_000 }).truncated).toBe(true);
  });

  it("survives an empty set, a single page and an offset past the end", () => {
    const empty = pagerModel({ total: 0, offset: 0, limit: 50, shown: 0 });
    expect(empty.pages).toBe(1);
    expect(empty.numbers).toEqual([1]);
    expect(empty.from).toBe(0);
    expect(empty.to).toBe(0);

    const past = page({ offset: 999_999, shown: 0 });
    // Clamped to the last page rather than reported as page 20,000 of 235.
    expect(past.current).toBe(235);
    expect(past.from).toBe(0);
  });
});

describe("pageOffset", () => {
  const at = (query: string, limit = 50) =>
    pageOffset(new URLSearchParams(query), limit);

  it("reads ?offset= as the API's own parameter", () => {
    expect(at("offset=100")).toBe(100);
    expect(at("")).toBe(0);
  });

  it("turns ?page= into an offset for the jump box", () => {
    expect(at("page=1")).toBe(0);
    expect(at("page=3")).toBe(100);
    expect(at("page=3", 20)).toBe(40);
  });

  it("lets a link's ?offset= win over a ?page= beside it", () => {
    // Both arrive when a jump form carries an offset through as a hidden
    // field, which is why no caller does — and why this is defined either way.
    expect(at("offset=150&page=2")).toBe(150);
  });

  it("takes a mistyped page as the first one rather than as an error", () => {
    expect(at("page=nonsense")).toBe(0);
    expect(at("page=0")).toBe(0);
    expect(at("page=-4")).toBe(0);
    expect(at("page=2.5")).toBe(50);
  });
});

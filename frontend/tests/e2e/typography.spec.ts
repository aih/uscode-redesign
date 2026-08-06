/**
 * The statute typography spec, asserted against a rendered page (ADR-0054).
 *
 * Everything here is geometry, persistence or paged media — the three things a
 * unit test on the renderer cannot answer and a stylesheet cannot promise. The
 * markup side (which elements are rungs, that a block quotation is a
 * `<blockquote>`, that a table arrives inside a focusable region) is in
 * `tests/uslm.test.ts`, where it runs without a browser.
 *
 * The depth the ladder has to hold is not written down here twice: it is read
 * out of `docs/verification/ladder.json`, which `scripts/ladder.py` measures
 * from the committed samples.
 *
 * Needs the site running: `make dev-all`.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

const LADDER = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../../../docs/verification/ladder.json", import.meta.url)),
    "utf8",
  ),
);

/** A real section from the CI fixture corpus, with subsections and paragraphs
 *  under them. `/app/design`'s specimen goes five deep and reaches no data, so
 *  it is the one used where depth matters more than reality. */
const SECTION = "/app/us/usc/t16/s45f";
const DESIGN = "/app/design";

/** Every `.prov` on the page, with its nesting depth and the two x-positions
 *  the ladder is a claim about: where the box starts, and where its number
 *  starts. Relative to the reading column, so the copy gutter cancels out. */
async function ladder(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const origin = document.querySelector(".section-body")!.getBoundingClientRect().left;
    return [...document.querySelectorAll(".section-body .prov")].map((el) => {
      let depth = 0;
      for (let a = el.parentElement; a; a = a.parentElement) {
        if (a.classList.contains("prov")) depth += 1;
      }
      const num = el.querySelector(":scope > .uslm-num");
      const box = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      // Sub-pixel throughout. The step is 25.2px, so rounding the positions
      // makes consecutive differences alternate between 25 and 26 and the
      // ladder looks uneven when it is exact.
      const at = (value: number) => Math.round((value - origin) * 100) / 100;
      return {
        depth,
        boxLeft: at(box.left),
        textLeft: at(box.left + parseFloat(style.paddingLeft)),
        numLeft: num ? at(num.getBoundingClientRect().left) : null,
        step: Math.round(parseFloat(style.paddingLeft) * 100) / 100,
      };
    });
  });
}

test.describe("the subsection ladder", () => {
  test("indents one step per level, cumulatively", async ({ page }) => {
    await page.goto(DESIGN);
    const rungs = await ladder(page);

    // The design page's specimen goes to depth 4 — (a), (1), (A), (i), (I) —
    // which is what makes it worth asserting against rather than § 45f's two.
    expect(Math.max(...rungs.map((r) => r.depth))).toBeGreaterThanOrEqual(4);

    const step = rungs[0].step;
    expect(step).toBeGreaterThan(0);

    // One offset per depth, and each exactly one step further than the last.
    // This is the assertion the whole feature is: before ADR-0054 every rung
    // reported the same `boxLeft`, and after the source's own `indentN`
    // classes were left composing with it, two siblings at one depth reported
    // two different ones.
    const byDepth = new Map<number, Set<number>>();
    for (const rung of rungs) {
      if (!byDepth.has(rung.depth)) byDepth.set(rung.depth, new Set());
      byDepth.get(rung.depth)!.add(rung.boxLeft);
    }
    for (const [depth, offsets] of byDepth) {
      expect(offsets.size, `depth ${depth} sits at one offset`).toBe(1);
    }

    const depths = [...byDepth.keys()].sort((a, b) => a - b);
    for (const depth of depths.slice(1)) {
      const here = [...byDepth.get(depth)!][0];
      const above = [...byDepth.get(depth - 1)!][0];
      expect(here - above, `depth ${depth} is one step in from ${depth - 1}`).toBeCloseTo(
        step,
        1,
      );
    }
  });

  test("hangs the number at the parent's text edge", async ({ page }) => {
    await page.goto(DESIGN);
    const rungs = await ladder(page);

    // The number is pulled back by exactly the step its own box added, so a
    // rung's number starts where its parent's text starts. `--indent-step` was
    // in `ch` first, and `.uslm-num` is bold: 3ch of Spectral Bold is 3px
    // wider than 3ch of Spectral, and every number overhung by that much.
    for (const rung of rungs) {
      expect(rung.numLeft, `depth ${rung.depth} number hangs to its box edge`).toBeCloseTo(
        rung.boxLeft,
        1,
      );
    }

    const byDepth = new Map<number, { textLeft: number; numLeft: number | null }>();
    for (const rung of rungs) byDepth.set(rung.depth, rung);
    for (const [depth, rung] of byDepth) {
      if (depth === 0) continue;
      expect(
        rung.numLeft,
        `depth ${depth} numbers align with depth ${depth - 1} text`,
      ).toBeCloseTo(byDepth.get(depth - 1)!.textLeft, 1);
    }
  });

  test("still leaves a column to read in at 320 CSS px", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 800 });
    await page.goto(DESIGN);

    const rungs = await ladder(page);
    const deepest = Math.max(...rungs.map((r) => r.textLeft));
    const column = await page.evaluate(
      () => document.querySelector(".section-body")!.getBoundingClientRect().width,
    );

    // The step degrades below 40em rather than the text wrapping under the
    // number. What is left has to be a column and not a gutter: the corpus
    // reaches depth 7 (`ladder.json`), so the budget is checked against that
    // rather than against the specimen's 4.
    const corpusDepth = Number(
      Object.keys(LADDER.sectionsByMaxDepth).sort((a, b) => Number(b) - Number(a))[0],
    );
    expect(corpusDepth).toBeGreaterThanOrEqual(7);

    const step = rungs[0].step;
    const worstCase = column - corpusDepth * step;
    expect(worstCase, `${corpusDepth} steps of ${step}px leaves a readable column`)
      .toBeGreaterThan(150);
    expect(deepest).toBeLessThan(column / 2);
  });

  test("the page does not scroll sideways at 320 CSS px", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 800 });
    await page.goto(SECTION);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBe(0);
  });
});

test.describe("the five kinds of text", () => {
  test("sets the law in the reading face and the apparatus in the interface face", async ({
    page,
  }) => {
    await page.goto(DESIGN);

    const faces = await page.evaluate(() => {
      const family = (selector: string) => {
        const el = document.querySelector(selector);
        return el ? getComputedStyle(el).fontFamily.split(",")[0].replace(/["']/gu, "") : null;
      };
      return {
        operative: family(".section-body .uslm-content"),
        quoted: family(".section-body blockquote.uslm-quotedContent"),
        note: family(".section-body .uslm-note"),
        credit: family(".section-body .uslm-sourceCredit"),
        table: family(".section-body .uslm-table"),
      };
    });

    expect(faces.operative).toBe("Spectral");
    // Quoted amending text is statutory text and keeps the reading face, even
    // though it almost always sits inside a note that does not.
    expect(faces.quoted).toBe("Spectral");
    expect(faces.note).toBe("Archivo");
    expect(faces.credit).toBe("Archivo");
    expect(faces.table).toBe("Archivo");
  });

  test("never justifies statutory text", async ({ page }) => {
    await page.goto(SECTION);
    const aligns = await page.evaluate(() =>
      [...document.querySelectorAll(".section-body .uslm-content, .section-body .prov")]
        .map((el) => getComputedStyle(el).textAlign)
        .filter((value, i, all) => all.indexOf(value) === i),
    );
    expect(aligns).not.toContain("justify");
  });
});

test.describe("reading density", () => {
  test("defaults to comfortable, switches, and is remembered", async ({ page }) => {
    await page.goto(SECTION);

    const read = () =>
      page.evaluate(() => {
        const text = getComputedStyle(document.querySelector(".section-body")!);
        return {
          density: document.documentElement.dataset.density ?? null,
          size: parseFloat(text.fontSize),
          leading: parseFloat(text.lineHeight),
          // The reading column itself, not `.reader-wrap`: a section page has
          // a rail, so its wrapper is `--measure-wide` and the prose is the
          // grid track inside it. That track is what has to narrow.
          measure: Math.round(
            document.querySelector(".section-body")!.getBoundingClientRect().width,
          ),
          height: Math.round(document.querySelector(".section-body")!.scrollHeight),
        };
      });

    const comfortable = await read();
    expect(comfortable.density).toBeNull();

    await page.locator(".density-toggle").click();
    const compact = await read();

    expect(compact.density).toBe("compact");
    expect(compact.size).toBeLessThan(comfortable.size);
    expect(compact.leading).toBeLessThan(comfortable.leading);
    // The column narrows with the text — `--measure` is a multiple of
    // `--reading-size` — which is what keeps the character count the same.
    expect(compact.measure).toBeLessThan(comfortable.measure);
    expect(compact.height).toBeLessThan(comfortable.height);

    await page.reload();
    expect((await read()).density).toBe("compact");

    await page.locator(".density-toggle").click();
    expect((await read()).density).toBe("comfortable");
  });

  test("arrives before first paint rather than reflowing the column", async ({ page }) => {
    await page.goto(SECTION);
    await page.locator(".density-toggle").click();

    // The attribute has to be on <html> by the time the first stylesheet-driven
    // layout happens. Read it before the page has finished loading: the
    // bootstrap is a blocking script in <head>, so it has run and the islands
    // have not.
    await page.goto(SECTION, { waitUntil: "commit" });
    const atCommit = await page.evaluate(() => document.documentElement.dataset.density);
    expect(atCommit).toBe("compact");
  });

  test("does not move the theme toggle when it changes", async ({ page }) => {
    await page.goto(SECTION);
    const before = await page.locator(".theme-toggle").boundingBox();
    await page.locator(".density-toggle").click();
    const after = await page.locator(".theme-toggle").boundingBox();

    // The label names the destination, so it alternates between two words of
    // different length. Without a reserved width the control beside it jumps.
    expect(Math.round(after!.x)).toBe(Math.round(before!.x));
  });

  test("costs the sticky stack nothing", async ({ page }) => {
    // Adding a control to `.navtools` is a change to `--sticky-h` if it wraps
    // the row, and that token is what `scroll-margin-top` spends (CLAUDE.md
    // says so by name). It does not wrap at the widths where the stack sticks.
    for (const width of [700, 1024, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(SECTION);
      const cost = await page.evaluate(() => {
        const header = document.querySelector(".usa-header") as HTMLElement;
        const control = document.querySelector(".density-toggle") as HTMLElement;
        const withIt = header.getBoundingClientRect().height;
        control.style.display = "none";
        const without = header.getBoundingClientRect().height;
        control.style.display = "";
        return withIt - without;
      });
      expect(cost, `the control costs no header height at ${width}px`).toBe(0);
    }
  });
});

test.describe("printing", () => {
  test.beforeEach(async ({ page }) => {
    await page.emulateMedia({ media: "print" });
  });

  test("drops the chrome and keeps the document", async ({ page }) => {
    await page.goto(SECTION);

    for (const gone of [".usa-header", ".usa-footer", ".copycol", ".rail", ".rpswitch"]) {
      const count = await page.locator(gone).count();
      if (count === 0) continue;
      await expect(page.locator(gone).first(), `${gone} is not printed`).toBeHidden();
    }

    await expect(page.locator(".section-body")).toBeVisible();
    // The release facts stay. They are a statement about the text on the page,
    // not a control, and a printout that does not carry them is statutory text
    // of unknown vintage.
    await expect(page.locator(".releasebar")).toBeVisible();
  });

  test("carries the citation and the release point in a running header", async ({ page }) => {
    await page.goto(`${SECTION}?release=119-102not101`);

    const head = page.locator(".printhead");
    await expect(head).toBeVisible();
    await expect(head).toContainText("16 U.S.C. § 45f");
    await expect(head).toContainText("119-102not101");

    // In the page's top margin rather than over the first line of it: `@page`
    // reserves the band and this hangs up into it, which is what makes it
    // repeat on every sheet without covering anything.
    const top = await head.evaluate((el) => getComputedStyle(el).top);
    expect(parseFloat(top)).toBeLessThan(0);
    expect(await head.evaluate((el) => getComputedStyle(el).position)).toBe("fixed");
  });

  test("prints the URL of every cross reference", async ({ page }) => {
    await page.goto(`${SECTION}?release=119-102not101`);

    const printed = await page.evaluate(() => {
      const link = document.querySelector(".section-body a[data-cite]");
      if (!link) return null;
      return {
        url: link.getAttribute("data-print-url"),
        after: getComputedStyle(link, "::after").content,
      };
    });

    expect(printed, "the fixture section carries a cross reference").not.toBeNull();
    // The citation URL, not the reader's own `/app` path, and carrying the
    // release so the printed reference resolves to the vintage it came from.
    expect(printed!.url).toMatch(/^\/us\/usc\//u);
    expect(printed!.url).toContain("release=119-102not101");
    expect(printed!.after).toContain(printed!.url);
  });

  test("opens the notes and the source credit", async ({ page }) => {
    await page.goto(SECTION);

    // Chromium implements `::details-content`, which is the hook the print
    // block uses. A browser without it prints whatever state the reader left,
    // recorded as ADR-0054's cost.
    const notes = page.locator(".uslm-notes").first();
    if ((await notes.count()) === 0) test.skip();
    const height = await notes.evaluate((el) => el.getBoundingClientRect().height);
    const summary = await notes
      .locator("summary")
      .evaluate((el) => el.getBoundingClientRect().height);
    expect(height, "the notes are taller than their own summary row").toBeGreaterThan(
      summary * 2,
    );
  });
});

/**
 * The design system page agrees with the committed contrast artifact (ADR-0053).
 *
 * `/app/design` computes its contrast ratios in the browser, from the tokens
 * the page has actually resolved, so the table is right in whichever theme is
 * on. `scripts/contrast.py` computes the same pairs from `site.scss` and writes
 * `docs/verification/contrast.json`. Two implementations of one formula, and
 * this is what stops them drifting: every pair, in both themes, compared digit
 * for digit against the artifact.
 *
 * Either one alone would be weaker. The artifact cannot see a colour the page
 * paints from something other than the token (ADR-0042's `.usa-nav__link`); the
 * page alone is a second unchecked source of numbers.
 *
 * Needs the site running: `make dev-all`.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

const ARTIFACT = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../../../docs/verification/contrast.json", import.meta.url)),
    "utf8",
  ),
);

const PAGE = "/app/design";

interface Row {
  fg: string;
  bg: string;
  ratio: string | null;
  text: string;
}

/** Every row of the page's pair table, as the page computed it. */
async function rows(page: Page): Promise<Row[]> {
  return page.$$eval("[data-pair-fg]", (found) =>
    found.map((row) => {
      const cell = row.querySelector("[data-pair-result]") as HTMLElement;
      return {
        fg: (row as HTMLElement).dataset.pairFg ?? "",
        bg: (row as HTMLElement).dataset.pairBg ?? "",
        ratio: cell.dataset.ratio ?? null,
        text: cell.textContent ?? "",
      };
    }),
  );
}

for (const theme of ["light", "dark"] as const) {
  test(`the contrast table matches contrast.json in ${theme}`, async ({ page }) => {
    // Before any document script, so the pre-paint bootstrap in `Base.astro`
    // stamps the attribute and the table is computed once, already themed.
    await page.addInitScript((value) => {
      try {
        localStorage.setItem("usc-theme", value);
      } catch {
        /* a browser refusing storage is not this test's subject */
      }
    }, theme);
    await page.goto(PAGE, { waitUntil: "load" });
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);

    const measured = await rows(page);
    expect(
      measured.length,
      "the page renders a row per declared pair",
    ).toBe(ARTIFACT.pairs.length);

    for (const [index, pair] of ARTIFACT.pairs.entries()) {
      const row = measured[index];
      expect(`${row.fg} on ${row.bg}`).toBe(`${pair.foreground} on ${pair.background}`);

      const expected = pair[theme];
      if (expected.skipped) {
        expect(row.text).toContain("not an opaque colour");
        continue;
      }
      expect(
        Number(row.ratio),
        `${pair.usage} [${theme}]: the page computed ${row.ratio}:1 from the rendered tokens, ` +
          `docs/verification/contrast.json has ${expected.ratio}:1 from site.scss. One of them ` +
          `is measuring something the other is not — re-run \`uv run python scripts/contrast.py\` ` +
          `and, if it still disagrees, a rule is painting a colour the token does not name.`,
      ).toBeCloseTo(expected.ratio, 2);

      // The verdict, not just the number: a pair whose requirement changed in
      // color-pairs.json without the ratio moving would otherwise pass here.
      if (expected.passes === null) expect(row.text).not.toMatch(/pass|FAIL/);
      else expect(row.text).toContain(expected.passes ? "pass" : "FAIL");
    }
  });
}

test("every declared colour token has a swatch showing its resolved value", async ({ page }) => {
  await page.goto(PAGE);

  const swatches = await page.$$eval("[data-swatch-value]", (found) =>
    found.map((el) => ({
      token: (el as HTMLElement).dataset.swatchValue ?? "",
      value: el.textContent ?? "",
    })),
  );

  const declared = new Set(
    ARTIFACT.pairs.flatMap((pair: { foreground: string; background: string }) => [
      pair.foreground,
      pair.background,
    ]),
  );
  expect(new Set(swatches.map((s) => s.token))).toEqual(declared);
  for (const swatch of swatches) {
    expect(swatch.value, `${swatch.token} resolved to nothing`).not.toBe("unset");
  }
});

test("the page reaches no data, so it renders the same on any corpus", async ({ page }) => {
  // Every other reader route's appearance depends on what is loaded. This one
  // is a fixed target for `make shots` and the axe matrix, and it is only fixed
  // for as long as nothing on it calls the API.
  const calls: string[] = [];
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (path.startsWith("/api/") || path.startsWith("/app/preview")) calls.push(path);
  });

  await page.goto(PAGE);
  await expect(page.locator(".section-body")).toBeVisible();
  expect(calls, "/app/design asked the API for something").toEqual([]);
});

test.describe("the version timeline's two views (ADR-0075)", () => {
  // The fixture corpus's two release points produce only `initial` and `text`
  // transitions, so this page is the only place CI can see a notes-only or
  // metadata-only entry — and the only place the filtering is checkable.
  test("the default view hides the notes-only and metadata-only entries", async ({ page }) => {
    await page.goto(PAGE);
    const text = page.locator('.timeline[data-view="text"]');
    const all = page.locator('.timeline[data-view="all"]');

    await expect(text.locator("li")).toHaveCount(5);
    await expect(text.locator('li[data-change-kind="notes"]')).toBeHidden();
    await expect(text.locator('li[data-change-kind="structure"]').first()).toBeHidden();
    await expect(text.locator('li[data-change-kind="text"]').first()).toBeVisible();

    await expect(all.locator('li[data-change-kind="notes"]')).toBeVisible();
    await expect(all.locator('li[data-change-kind="structure"]').first()).toBeVisible();
  });

  test("a shown entry's run covers the entries the default view hides", async ({ page }) => {
    await page.goto(PAGE);
    const text = page.locator('.timeline[data-view="text"]');
    const all = page.locator('.timeline[data-view="all"]');

    // The oldest entry carries 119-95 and 119-96 of its own and stands through
    // the metadata-only entry at 119-97.
    await expect(
      text.locator("li").first().locator(".timeline__releases:visible"),
    ).toContainText("119-97");
    await expect(
      all.locator("li").first().locator(".timeline__releases:visible"),
    ).not.toContainText("119-97");
  });

  test("an attributed amendment carries its law chips", async ({ page }) => {
    await page.goto(PAGE);
    const chips = page.locator('.timeline[data-view="text"] .timeline__law');
    await expect(chips).toHaveCount(2);
    await expect(chips.first()).toContainText("Pub. L. 119–14");
    await expect(chips.last()).toContainText("new");
    await expect(chips.first()).toHaveAttribute("href", /\/app\/classification\?q=/u);
  });

  test("an unattributed amendment says no statute is recorded", async ({ page }) => {
    await page.goto(PAGE);
    await expect(
      page.locator('.timeline[data-view="text"] li').last().locator(".timeline__kind"),
    ).toContainText("No classifying statute recorded");
  });
});

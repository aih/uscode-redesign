/**
 * Asking a diff for its source-level redline.
 *
 * The redline is rendered in the page (`lib/xmlredline.ts`), not linked away to
 * the API's JSON — so every link that offers it has to land the reader on the
 * "Source XML" panel, clear of the sticky chrome, and say something while the
 * server recomputes the expensive diff. None of that is answerable outside a
 * browser: the scroll position depends on `--sticky-h`, and the indicator only
 * exists between the click and the next paint.
 */
import { expect, test } from "@playwright/test";

import { gotoDiff, settleDiff } from "./ratelimited";

// Two release points the dev/CI database actually holds (`make dev-data` /
// `make ci-data`), for a section whose text changed between them.
const DIFF = "/app/diff/us/usc/t16/s2201?from=119-99&to=119-102not101";

test("the source link renders the redline in the page, not as JSON", async ({ page }) => {
  await gotoDiff(page, DIFF);
  await expect(page.locator(".diff-view--source")).toHaveCount(0);

  await page.getByRole("link", { name: /source redline/i }).click();
  await page.waitForLoadState("load");
  await settleDiff(page);

  // Same site, same page — the panel, not `/api/v1/…/diff`.
  expect(new URL(page.url()).pathname).toBe(new URL(DIFF, page.url()).pathname);
  await expect(page.locator(".diff-view--source")).toBeVisible({ timeout: 30_000 });
});

test("it scrolls to the panel, clear of the sticky chrome", async ({ page }) => {
  await gotoDiff(page, `${DIFF}&source=1#source`);
  await page.waitForTimeout(400);

  const heading = page.locator("#source");
  await expect(heading).toBeInViewport();

  // In viewport is not enough: `#source` is an anchor target like any other and
  // pays the same `--sticky-h` toll, or it lands *underneath* the header. Ask
  // the browser what is actually painted at the heading's own top edge.
  const covered = await page.evaluate(() => {
    const box = document.querySelector("#source")!.getBoundingClientRect();
    const at = document.elementFromPoint(box.left + 2, box.top + 2);
    return !(at && (at.id === "source" || at.closest("#source")));
  });
  expect(covered).toBe(false);
});

test("a slow render says so instead of looking dead", async ({ page }) => {
  await gotoDiff(page, DIFF);

  // The indicator lives between the click and the next paint, so it cannot be
  // asserted from outside: any Playwright query races the navigation the click
  // starts, and the document it would query is already gone. The click is
  // dispatched and the DOM read in the *same* task instead — handlers have run,
  // the navigation has not yet been serviced.
  const shown = await page.evaluate(() => {
    document.querySelector<HTMLAnchorElement>("a[data-source-render]")!.click();
    const status = document.querySelector(".sourceload");
    return {
      text: status?.textContent ?? null,
      role: status?.getAttribute("role") ?? null,
      spinner: Boolean(status?.querySelector(".sourceload__spin")),
    };
  });

  expect(shown.text).toMatch(/rendering the source redline/i);
  // The wait is the message: a reader who cannot see the spinner is told too.
  expect(shown.role).toBe("status");
  expect(shown.spinner).toBe(true);

  await page.waitForLoadState("load");
  await settleDiff(page);
  await expect(page.locator(".diff-view--source")).toBeVisible({ timeout: 30_000 });
});

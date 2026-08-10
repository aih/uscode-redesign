/**
 * The command palette (ADR-0062).
 *
 * Vitest covers the rows as data — which release point "the previous one" is,
 * and that every href goes through `url.ts`. What only a browser answers is
 * whether the key fires at all, where the keyboard ends up afterwards, and
 * whether the two modals on the page get in each other's way.
 *
 * `ControlOrMeta` rather than `Meta`: the binding is one shortcut printed two
 * ways (`lib/shortcuts.ts`), and CI runs on Linux while this machine does not.
 *
 * Needs the site running: `make dev-all`, then `make test-e2e`.
 */
import { expect, test } from "@playwright/test";

const SECTION = "/app/us/usc/t16/s45f";
/** No section on screen, so the two per-page rows have nothing to act on. */
const RELEASES = "/app/releases";
const PALETTE = "#palette";

type Page = import("@playwright/test").Page;

/** The id or class of whatever has focus. */
const focused = (page: Page) =>
  page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el) return "none";
    return el.id || el.dataset.paletteId || el.className || el.tagName;
  });

test("⌘K opens it and puts the keyboard in the box", async ({ page }) => {
  await page.goto(SECTION, { waitUntil: "load" });
  await expect(page.locator(PALETTE)).toBeHidden();

  await page.locator("body").press("ControlOrMeta+k");

  await expect(page.locator(PALETTE)).toBeVisible();
  expect(await focused(page)).toBe("palette-q");
});

test("⌘K works while the reader is typing, which no other shortcut does", async ({ page }) => {
  await page.goto(SECTION, { waitUntil: "load" });
  const box = page.locator("#site-q");
  await box.click();
  await box.fill("conservation");

  // `k` alone here is a character in a search box, and must stay one.
  await box.press("k");
  await expect(page.locator(PALETTE)).toBeHidden();
  await expect(box).toHaveValue("conservationk");

  await box.press("ControlOrMeta+k");
  await expect(page.locator(PALETTE)).toBeVisible();
});

test("Escape closes it and hands the keyboard back to where it came from", async ({ page }) => {
  await page.goto(SECTION, { waitUntil: "load" });
  const box = page.locator("#site-q");
  await box.click();
  expect(await focused(page)).toBe("site-q");

  await box.press("ControlOrMeta+k");
  await expect(page.locator(PALETTE)).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(page.locator(PALETTE)).toBeHidden();
  expect(await focused(page)).toBe("site-q");
});

test("the box submits to /app/goto, the same router the header's box posts to", async ({ page }) => {
  await page.goto(SECTION, { waitUntil: "load" });
  await page.locator("body").press("ControlOrMeta+k");
  await page.locator("#palette-q").fill("16 usc 45f");
  await page.locator("#palette-q").press("Enter");

  await expect(page).toHaveURL(/\/app\/us\/usc\/t16\/s45f/u);
  await expect(page.locator(".doc-title")).toContainText("45f");
});

test("a section offers the redline against the release point before this one", async ({ page }) => {
  await page.goto(SECTION, { waitUntil: "load" });
  await page.locator("body").press("ControlOrMeta+k");

  const compare = page.locator('[data-palette-id="compare-previous"]');
  await expect(compare).toBeVisible();
  await compare.click();

  await expect(page).toHaveURL(/\/app\/diff\/us\/usc\/t16\/s45f\?from=.+&to=.+/u);
  await expect(page.locator("h1")).toContainText("45f");
});

test("a page with no section on it offers neither of the section rows", async ({ page }) => {
  await page.goto(RELEASES, { waitUntil: "load" });
  await page.locator("body").press("ControlOrMeta+k");

  await expect(page.locator(PALETTE)).toBeVisible();
  await expect(page.locator('[data-palette-id="compare-previous"]')).toHaveCount(0);
  await expect(page.locator('[data-palette-id="versions"]')).toHaveCount(0);
  await expect(page.locator('[data-palette-id="guide"]')).toBeVisible();
});

test("typing narrows the commands, and says so when nothing is left", async ({ page }) => {
  await page.goto(SECTION, { waitUntil: "load" });
  await page.locator("body").press("ControlOrMeta+k");

  const rows = page.locator("[data-palette-row]:visible");
  const all = await rows.count();
  expect(all).toBeGreaterThan(4);

  await page.locator("#palette-q").fill("version");
  await expect(rows).toHaveCount(1);
  await expect(page.locator('[data-palette-id="versions"]')).toBeVisible();
  await expect(page.locator("[data-palette-empty]")).toBeHidden();

  await page.locator("#palette-q").fill("zzzzqqqq");
  await expect(rows).toHaveCount(0);
  await expect(page.locator("[data-palette-empty]")).toBeVisible();

  // Cleared, not emptied: an empty box is every command, not no commands.
  await page.locator("#palette-q").fill("");
  await expect(rows).toHaveCount(all);
  await expect(page.locator("[data-palette-empty]")).toBeHidden();
});

test("↓ and ↑ move focus itself between the rows and back to the box", async ({ page }) => {
  await page.goto(SECTION, { waitUntil: "load" });
  await page.locator("body").press("ControlOrMeta+k");

  await page.keyboard.press("ArrowDown");
  expect(await focused(page)).toBe("compare-previous");

  await page.keyboard.press("ArrowDown");
  expect(await focused(page)).toBe("versions");

  await page.keyboard.press("ArrowUp");
  expect(await focused(page)).toBe("compare-previous");

  await page.keyboard.press("ArrowUp");
  expect(await focused(page)).toBe("palette-q");
});

test("↓ skips the rows a query filtered out", async ({ page }) => {
  await page.goto(SECTION, { waitUntil: "load" });
  await page.locator("body").press("ControlOrMeta+k");
  await page.locator("#palette-q").fill("guide");

  await page.keyboard.press("ArrowDown");
  expect(await focused(page)).toBe("guide");
});

test("the shortcut row swaps one modal for the other rather than stacking them", async ({
  page,
}) => {
  await page.goto(SECTION, { waitUntil: "load" });
  await page.locator("body").press("ControlOrMeta+k");
  await page.locator('[data-palette-id="shortcuts"]').click();

  await expect(page.locator("#shortcuts")).toBeVisible();
  await expect(page.locator(PALETTE)).toBeHidden();

  // One Escape, not two.
  await page.keyboard.press("Escape");
  await expect(page.locator("#shortcuts")).toBeHidden();
});

test("the section keys stay quiet behind it", async ({ page }) => {
  await page.goto(SECTION, { waitUntil: "load" });
  const start = await page.evaluate(() => Math.round(window.scrollY));

  await page.locator("body").press("ControlOrMeta+k");
  // Focus is in the input, so this is typing; the rows are what it filters.
  await page.keyboard.press("n");
  await page.keyboard.press("b");

  await expect(page.locator(PALETTE)).toBeVisible();
  expect(await page.evaluate(() => Math.round(window.scrollY))).toBe(start);
});

/**
 * `make shots` carries the horizontal-overflow ratchet for WCAG 1.4.10, and it
 * cannot reach this: the dialog is closed on every page it photographs, so a
 * palette wider than a 320px viewport would be a failure nothing measures.
 */
test.describe("at a phone width", () => {
  test.use({ viewport: { width: 320, height: 768 } });

  test("it fits the viewport and scrolls inside itself", async ({ page }) => {
    await page.goto(SECTION, { waitUntil: "load" });
    await page.locator("body").press("ControlOrMeta+k");
    await expect(page.locator(PALETTE)).toBeVisible();

    const box = await page.evaluate(() => {
      const dialog = document.getElementById("palette")!;
      const rect = dialog.getBoundingClientRect();
      return {
        pageWidth: document.documentElement.scrollWidth,
        viewport: window.innerWidth,
        left: rect.left,
        right: rect.right,
        overflows: dialog.scrollHeight > dialog.clientHeight,
        clipped: rect.bottom > window.innerHeight,
      };
    });

    expect(box.pageWidth, "the page scrolls sideways behind the palette").toBeLessThanOrEqual(
      box.viewport,
    );
    expect(box.left).toBeGreaterThanOrEqual(0);
    expect(box.right).toBeLessThanOrEqual(box.viewport);
    // Taller than the screen is fine; taller than the screen with no way to
    // reach the bottom is not.
    expect(box.clipped && !box.overflows, "the last rows are unreachable").toBe(false);
  });
});

test("the shortcut list prints the key, so a reader can find it without knowing it", async ({
  page,
}) => {
  await page.goto(SECTION, { waitUntil: "load" });
  await page.locator("body").press("Shift+Slash");

  await expect(page.locator("#shortcuts")).toContainText("⌘K");
  await expect(page.locator("#shortcuts")).toContainText("Ctrl K");
});

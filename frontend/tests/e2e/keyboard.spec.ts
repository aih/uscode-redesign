/**
 * Navigation inside a section, and the keyboard map that reaches it (ADR-0055).
 *
 * Vitest covers the data — `outline()`'s rows, `keyMap()`'s bindings, and that
 * every printed action has an arm in the island. None of that answers the
 * questions here, which are all about a real document: whether a key fires,
 * where the scroll position ends up, whether focus went with it, and whether a
 * modal actually traps.
 *
 * The guide's own scenarios (ADR-0038) cover the happy path for `?`, `n`, `/`
 * and the contents list. What is here is the rest: the edges, the refusals, and
 * the two things that were wrong the first time — `]` landing on the provision
 * it started from, and a jump that moved the scroll position without moving the
 * keyboard.
 *
 * Needs the site running: `make dev-all`, then `make test-e2e`.
 */
import { expect, test } from "@playwright/test";

/** A section with subsections, a source credit and notes. */
const SECTION = "/app/us/usc/t16/s45f";
/** No section, so the section-only keys have nothing to act on. */
const RELEASES = "/app/releases";
const DIALOG = "#shortcuts";

type Page = import("@playwright/test").Page;

const scrollY = (page: Page) => page.evaluate(() => Math.round(window.scrollY));

/** Wait for a smooth scroll to finish, rather than guessing how long it takes.
 *
 * `scroll-behavior: smooth` has no completion event and no fixed duration —
 * the browser picks one from the distance — so a fixed timeout is a test that
 * passes on a short section and reads a mid-flight position on a long one.
 * That is exactly what it did here: 900 ms after `n` on § 45f the page was
 * 200px short of where it was going, and the next assertion compared against
 * the wrong number. */
async function settled(page: Page): Promise<number> {
  let last = -1;
  for (let i = 0; i < 40; i += 1) {
    const now = await scrollY(page);
    if (now === last) return now;
    last = now;
    await page.waitForTimeout(100);
  }
  return last;
}

/** The id or class of whatever has focus — what tells a jump apart from a
 *  scroll. */
const focused = (page: Page) =>
  page.evaluate(() => document.activeElement?.id || document.activeElement?.className || "");

test.describe("the section's own contents", () => {
  test("lists the top-level provisions, then the source credit and the notes", async ({
    page,
  }) => {
    await page.goto(SECTION);
    const rows = page.locator(".contents__link");
    await expect(rows.first()).toBeVisible();

    // Every row points at something that is actually in the document. A
    // contents list with a dead row is worse than no contents list.
    const dead = await page.evaluate(() =>
      [...document.querySelectorAll(".contents__link")]
        .map((a) => a.getAttribute("href")!.slice(1))
        .filter((id) => !document.getElementById(id)),
    );
    expect(dead).toEqual([]);

    await expect(page.locator('.contents__link[href="#section-source"]')).toBeVisible();
    await expect(page.locator('.contents__link[href="#section-notes"]')).toBeVisible();
  });

  test("names the apparatus once, however many notes the section has", async ({ page }) => {
    // `RenderOptions.anchors` is opt-in per document precisely so a nested
    // `<notes>` and a hover card cannot claim the same two fragment names.
    await page.goto(SECTION);
    await expect(page.locator("#section-source")).toHaveCount(1);
    await expect(page.locator("#section-notes")).toHaveCount(1);
  });

  test("the hover card's body claims no fragment name of its own", async ({ page }) => {
    await page.goto(SECTION);
    await page.locator("a[data-cite]").first().hover();
    await expect(page.locator("#cite-preview")).toBeVisible({ timeout: 5000 });
    // Still one of each: the card inserted another section's body into this
    // document and named nothing.
    await expect(page.locator("#section-source")).toHaveCount(1);
    await expect(page.locator("#section-notes")).toHaveCount(1);
  });
});

test.describe("the sticky bar's number returns to the top", () => {
  test("scrolls back without adding a row to the sticky stack", async ({ page }) => {
    await page.goto(SECTION);
    await page.evaluate(() => window.scrollTo(0, 3000));
    expect(await scrollY(page)).toBeGreaterThan(1000);

    await page.locator(".sectionbar__top").click();
    expect(await settled(page)).toBeLessThan(400);
  });
});

test.describe("keyboard shortcuts", () => {
  test("s and n reach the apparatus and take the keyboard with them", async ({ page }) => {
    await page.goto(SECTION);

    await page.keyboard.press("n");
    const atNotes = await settled(page);
    expect(atNotes).toBeGreaterThan(1000);
    // The half that makes it a jump rather than a scroll: Tab from here
    // continues in the notes, not at the top of the document.
    expect(await focused(page)).toBe("section-notes");

    await page.keyboard.press("s");
    const atSource = await settled(page);
    expect(await focused(page)).toBe("section-source");
    // The source credit is above the notes in the document, so this went up.
    expect(atSource).toBeLessThan(atNotes);
  });

  test("] advances rather than re-landing on the provision it started from", async ({
    page,
  }) => {
    // The first version compared each provision's top against zero. A jumped-to
    // provision sits under the sticky chrome at ~60px, which is greater than
    // zero, so "the next one below" kept finding the current one.
    await page.goto(SECTION);
    const seen: string[] = [];
    for (let i = 0; i < 3; i += 1) {
      await page.keyboard.press("]");
      await settled(page);
      seen.push(await focused(page));
    }
    expect(new Set(seen).size).toBe(3);
    expect(seen[0]).toContain("/us/usc/t16/s45f/");

    await page.keyboard.press("[");
    await settled(page);
    expect(await focused(page)).toBe(seen[1]);
  });

  test("t returns to the top of the page's content", async ({ page }) => {
    await page.goto(SECTION);
    await page.evaluate(() => window.scrollTo(0, 4000));
    await page.keyboard.press("t");
    expect(await settled(page)).toBeLessThan(400);
    expect(await focused(page)).toBe("main");
  });

  test("a key typed into the search box is left alone", async ({ page }) => {
    await page.goto(SECTION);
    await page.keyboard.press("/");
    await expect(page.locator("#site-q")).toBeFocused();

    await page.keyboard.type("junk");
    await expect(page.locator("#site-q")).toHaveValue("junk");
    // `j`, `u`, `n` and `k` are all bound. None of them fired.
    await expect(page).toHaveURL(/s45f/u);
  });

  test("a combination held with a modifier is the browser's", async ({ page }) => {
    await page.goto(SECTION);
    await page.keyboard.press("Control+k");
    await page.waitForTimeout(300);
    await expect(page).toHaveURL(/s45f/u);
  });

  test("the section keys do nothing on a page that is not a section", async ({ page }) => {
    await page.goto(RELEASES);
    for (const key of ["k", "u", "n", "s", "]"]) {
      await page.keyboard.press(key);
    }
    await page.waitForTimeout(400);
    await expect(page).toHaveURL(/releases/u);
  });
});

test.describe("the shortcut list", () => {
  test("? opens it, Escape closes it, and it traps focus while open", async ({ page }) => {
    await page.goto(SECTION);
    const dialog = page.locator(DIALOG);
    await expect(dialog).toBeHidden();

    await page.keyboard.press("Shift+Slash");
    await expect(dialog).toBeVisible();
    expect(
      await page.evaluate(() =>
        document.querySelector("#shortcuts")!.contains(document.activeElement),
      ),
    ).toBe(true);

    // Nothing behind the modal answers a key while it is up.
    const before = await scrollY(page);
    await page.keyboard.press("]");
    await page.waitForTimeout(400);
    expect(await scrollY(page)).toBe(before);

    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });

  test("prints every binding the island holds", async ({ page }) => {
    await page.goto(SECTION);
    await page.keyboard.press("Shift+Slash");
    await expect(page.locator(DIALOG)).toBeVisible();

    // The dialog is rendered from `lib/shortcuts.ts` and the island is bound
    // from the same list, so the count is the contract: a row here is a key
    // that fires, and a key that fires has a row.
    const printed = await page.locator(`${DIALOG} .shortcuts__row`).count();
    const bound = await page.evaluate(
      () =>
        Object.keys(
          JSON.parse(document.querySelector("[data-shortcut-keys]")!.textContent!),
        ).length,
    );
    // Two of the rows print a second key for the same action (← or j, → or k).
    expect(bound).toBe(printed + 2);
  });

  test("the footer link opens it rather than navigating", async ({ page }) => {
    await page.goto(SECTION);
    await page.locator("[data-shortcuts-open]").click();
    await expect(page.locator(DIALOG)).toBeVisible();
    await expect(page).toHaveURL(/s45f/u);
  });

  test("is on a page that is not a section", async ({ page }) => {
    await page.goto(RELEASES);
    await page.keyboard.press("Shift+Slash");
    await expect(page.locator(DIALOG)).toBeVisible();
  });
});

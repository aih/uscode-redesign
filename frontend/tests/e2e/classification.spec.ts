/**
 * The classification lookup, and the tables under it (ADR-0067).
 *
 * What only a browser can answer here is the combobox: a debounced request, an
 * `aria-activedescendant` that moves without focus moving, `Enter` following the
 * active row, `Escape` closing without losing the keyboard — and the fact that
 * with JavaScript switched off the same box is still a GET form that reaches the
 * same answers, because the parse is server-side.
 *
 * The rest is the reflow property `make shots` asserts as a screenshot: five
 * columns of fixed-width source data at 320 CSS px, scrolling inside their own
 * region rather than taking the page sideways.
 *
 * Answerable from the CI fixture corpus: `make ci-data` loads the 118th's
 * second session, the 110th's first, the 104th's whole-congress file and the
 * ECCT (`make ci-classification-data`).
 */
import { expect, test } from "@playwright/test";

const INDEX = "/app/classification";
const TABLE = "/app/classification/118/2";

test.describe("the classification lookup", () => {
  test("suggests, and Enter follows the active row", async ({ page }) => {
    await page.goto(INDEX, { waitUntil: "load" });
    const box = page.locator("[data-classlookup-input]");
    await box.click();
    await box.fill("118-42");

    const options = page.locator("[data-classlookup-list] [role='option']");
    await expect(options.first()).toBeVisible({ timeout: 5000 });
    // The roles are stamped by the island, so their presence is also the
    // assertion that the no-script markup was enhanced rather than shipped
    // announcing behaviour it lacked.
    await expect(box).toHaveAttribute("role", "combobox");
    await expect(box).toHaveAttribute("aria-expanded", "true");

    await page.keyboard.press("ArrowDown");
    const first = options.first();
    await expect(first).toHaveAttribute("aria-selected", "true");
    // Focus stays in the input; only the active descendant moves.
    await expect(box).toBeFocused();
    await expect(box).toHaveAttribute("aria-activedescendant", (await first.getAttribute("id"))!);

    await page.keyboard.press("Enter");
    await page.waitForURL(/\/app\/classification\/118\/\d\?pl=118-42/, { timeout: 5000 });
  });

  test("arrow keys wrap, and Escape closes without taking the keyboard", async ({ page }) => {
    await page.goto(INDEX, { waitUntil: "load" });
    const box = page.locator("[data-classlookup-input]");
    await box.click();
    await box.fill("118-42");
    const options = page.locator("[data-classlookup-list] [role='option']");
    await expect(options.first()).toBeVisible({ timeout: 5000 });

    // Up from nothing selected lands on the last row.
    await page.keyboard.press("ArrowUp");
    await expect(options.last()).toHaveAttribute("aria-selected", "true");

    await page.keyboard.press("Escape");
    await expect(page.locator("[data-classlookup-list]")).toBeHidden();
    await expect(box).toHaveAttribute("aria-expanded", "false");
    await expect(box).not.toHaveAttribute("aria-activedescendant", /.*/);
    await expect(box).toBeFocused();
  });

  test("is a plain GET form with scripting off", async ({ browser }) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    await page.goto(INDEX, { waitUntil: "load" });

    // No listbox at all: nothing stamped the roles on.
    await expect(page.locator("[data-classlookup-input]")).not.toHaveAttribute("role", "combobox");

    await page.locator("[data-classlookup-input]").fill("118-42");
    await page.locator(".classlookup__go").click();
    await page.waitForURL(/\/app\/classification\?q=118-42/, { timeout: 5000 });
    // The same parse, rendered as links rather than as a listbox.
    await expect(page.locator(".classfind__link").first()).toBeVisible();
    await expect(page.locator(".classfind__link").first()).toHaveAttribute(
      "href",
      /\/app\/classification\/118\/\d\?pl=118-42/,
    );
    await context.close();
  });
});

test.describe("a classification table", () => {
  test("does not push the page sideways at 320 CSS px", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 768 });
    await page.goto(TABLE, { waitUntil: "load" });
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, "the page scrolls sideways at 320 CSS px (WCAG 1.4.10)").toBeLessThanOrEqual(
      0,
    );
    // The table itself is wider than that, and scrolls inside its own region.
    const wrap = page.locator(".classtable__wrap");
    const scrollable = await wrap.evaluate((el) => el.scrollWidth > el.clientWidth);
    expect(scrollable, "the table should be the thing that scrolls").toBe(true);
    await expect(wrap).toHaveAttribute("tabindex", "0");
  });

  test("keeps its filters across a sort change and drops the offset", async ({ page }) => {
    await page.goto(`${TABLE}?pl=118-42&offset=50`, { waitUntil: "load" });
    await page.getByRole("link", { name: "U.S. Code order" }).click();
    await page.waitForURL(/sort=code/, { timeout: 5000 });
    expect(page.url()).toContain("pl=118-42");
    expect(page.url()).not.toContain("offset=");
  });

  test("dismisses one filter and keeps the rest", async ({ page }) => {
    await page.goto(`${TABLE}?pl=118-42&title=42`, { waitUntil: "load" });
    await page.locator(".filterpills__clear").first().click();
    await page.waitForURL(/\/app\/classification\/118\/2\?/, { timeout: 5000 });
    expect(page.url()).not.toContain("pl=118-42");
    expect(page.url()).toContain("title=42");
  });
});

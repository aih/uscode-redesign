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
    await page.waitForURL(
      (url) => url.pathname === "/app/classification" && url.searchParams.get("q") === "118-42",
      { timeout: 5000 },
    );
    // The scope select always posts its value, so a submission with no scope
    // carries an empty one; the page redirects it away. The redirect is a path:
    // an absolute one built from `Astro.url` carries the adapter's `localhost`
    // fallback rather than the proxy's host and port, and the browser follows it
    // off the site — which is a timeout here rather than a wrong page.
    expect(new URL(page.url()).searchParams.has("scope")).toBe(false);
    // The same parse, rendered as links rather than as a listbox.
    await expect(page.locator(".classfind__link").first()).toBeVisible();
    await expect(page.locator(".classfind__link").first()).toHaveAttribute(
      "href",
      /\/app\/classification\/118\/\d\?pl=118-42/,
    );
    await context.close();
  });
});

test.describe("the by-section view", () => {
  // `/classifications/code/…` defaults to 100 rows. The busiest sections are
  // past that — 42 U.S.C. § 1396a has 353 — so an unpaged view showed a total
  // it was not rendering, with nothing on screen saying which hundred.
  const BUSY = "/app/classification?title=18&section=3551";

  test("renders a page, says which page, and offers the next one", async ({ page }) => {
    await page.goto(BUSY, { waitUntil: "load" });
    const rows = page.locator(".classsection tbody tr");
    const count = await rows.count();
    expect(count).toBeGreaterThan(0);
    expect(count).toBeLessThanOrEqual(50);

    // Named by its text rather than by position: the first `.doc-meta` in this
    // view is the line saying the tables begin at the 104th Congress (ADR-0070).
    const meta = await page
      .locator(".classsection .doc-meta", { hasText: "Showing" })
      .first()
      .innerText();
    expect(meta).toMatch(/Showing 1–\d+ of \d+/);

    // `textContent`, not `innerText`: `.toc-group` is uppercased by CSS, and
    // `innerText` reports what is painted.
    const heading = (await page.locator("#classsection-heading").textContent()) ?? "";
    const total = Number(/([\d,]+) rows?/.exec(heading)![1].replace(/,/g, ""));
    if (total > count) {
      await page.getByRole("link", { name: /Next/ }).click();
      await page.waitForURL(/offset=/, { timeout: 5000 });
      expect(page.url()).toContain("title=18");
      expect(page.url()).toContain("section=3551");
    }
  });

  test("offers Code order for a title and not for one section", async ({ page }) => {
    // With the section fixed every row carries the same citation, so ordering
    // by it orders nothing — the option is offered where it means something
    // (ADR-0071).
    await page.goto(BUSY, { waitUntil: "load" });
    await expect(page.locator(".sortbar__option")).toHaveCount(1);
    await expect(page.locator(".sortbar__option--on")).toContainText("newest first");
    await expect(page.locator('.classtable th[aria-sort]')).toHaveCount(1);

    await page.goto("/app/classification?title=18", { waitUntil: "load" });
    await expect(page.locator(".sortbar__option")).toHaveCount(2);
    await page.getByRole("link", { name: "U.S. Code order" }).click();
    await page.waitForURL(/sort=code/, { timeout: 5000 });
    await expect(page.locator(".classsection .classtable")).toBeVisible();
    await expect(page.locator('.classtable th[aria-sort="ascending"]')).toContainText(
      "U.S. Code",
    );
  });

  test("dismissing the section pill widens the view to the whole title", async ({ page }) => {
    // The two filters are ordered rather than symmetric (ADR-0070): a title
    // without a section is a view, a section without a title is nothing.
    await page.goto(BUSY, { waitUntil: "load" });
    await page.getByLabel(/Remove the section filter/).click();

    await page.waitForURL(/title=18/, { timeout: 5000 });
    expect(page.url()).not.toContain("section=");
    await expect(page.locator("#classsection-heading")).toContainText("Title 18");
    await expect(page.getByLabel(/Remove the title filter/)).toBeVisible();
  });

  test("says so when the offset is past the end", async ({ page }) => {
    await page.goto(`${BUSY}&offset=999999`, { waitUntil: "load" });
    await expect(page.getByText(/past the last of/)).toBeVisible();
    expect(await page.locator(".classsection tbody tr").count()).toBe(0);
    expect(await page.locator(".pager").count()).toBe(0);
  });
});

test.describe("a mistyped URL still shows the table", () => {
  test("a fractional offset does not become a 422", async ({ page }) => {
    const response = await page.goto("/app/classification/118/2?offset=1.5", {
      waitUntil: "load",
    });
    expect(response?.status()).toBe(200);
    await expect(page.locator(".classtable")).toBeVisible();
  });

  test("an offset past the end says so instead of counting past the total", async ({ page }) => {
    await page.goto("/app/classification/118/2?offset=999999", { waitUntil: "load" });
    await expect(page.getByText(/past the last of/)).toBeVisible();
    await expect(page.locator("body")).not.toContainText("Showing 1,000,000");
    expect(await page.locator(".pager").count()).toBe(0);
  });

  test("a session with no table is one heading, not two", async ({ page }) => {
    const response = await page.goto("/app/classification/104/1", { waitUntil: "load" });
    expect(response?.status()).toBe(404);
    const headings = page.locator("main h1");
    expect(await headings.count()).toBe(1);
    await expect(headings.first()).toContainText("404");
  });
});

test.describe("the ECCT", () => {
  test("links no classification cell, because none carries an identifier", async ({ page }) => {
    // Composing `/us/usc/t{title}/s{section_norm}` 404ed on 7 of 30 links, every
    // one in the Former classification column — the column whose whole meaning
    // is that the provision moved away.
    await page.goto("/app/classification/ecct", { waitUntil: "load" });
    const cells = page.locator(".classtable__cite");
    expect(await cells.count()).toBeGreaterThan(0);
    expect(await cells.locator("a").count()).toBe(0);
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

  test("turns an order round from the sort bar and from the column heading", async ({
    page,
  }) => {
    // Four orders from two controls (ADR-0071): the option in force is a link
    // that reverses it, and the sorted column heading is the same control.
    await page.goto(TABLE, { waitUntil: "load" });
    const inForce = page.locator(".sortbar__option--on");
    await expect(inForce).toContainText("Public law order");
    await expect(inForce).toContainText("as published");

    await inForce.click();
    await page.waitForURL(/sort=pl-desc/, { timeout: 5000 });
    await expect(page.locator(".sortbar__option--on")).toContainText("reversed");

    await page.locator('[data-sort-column="code"]').click();
    await page.waitForURL(/sort=code/, { timeout: 5000 });
    // The other key starts in its own ascending direction rather than carrying
    // this one's across.
    expect(page.url()).not.toContain("code-desc");
    const sorted = page.locator('.classtable th[aria-sort="ascending"]');
    await expect(sorted).toHaveCount(1);
    await expect(sorted).toContainText("U.S. Code");
    await expect(page.locator('.classtable th[aria-sort="none"]')).toHaveCount(1);

    await page.locator('[data-sort-column="code"]').click();
    await page.waitForURL(/sort=code-desc/, { timeout: 5000 });
    await expect(page.locator('.classtable th[aria-sort="descending"]')).toHaveCount(1);
  });

  test("reads the rows in the order the URL asks for", async ({ page }) => {
    // The assertion is the two orders being reverses of each other, because the
    // CI corpus and the full one hold different rows and only their relation is
    // stable.
    const cites = async (sort: string) => {
      await page.goto(`${TABLE}?sort=${sort}`, { waitUntil: "load" });
      return page.$$eval(".classtable tbody th", (cells) =>
        cells.map((cell) => cell.textContent?.trim() ?? ""),
      );
    };
    const up = await cites("code");
    const down = await cites("code-desc");
    expect(up.length).toBeGreaterThan(1);
    // Only the first page of each, so the two lists are the ends of one
    // ordering rather than the same list backwards.
    expect(down[0]).not.toBe(up[0]);
  });

  test("numbers its pages, and the first page has no previous", async ({ page }) => {
    await page.goto(TABLE, { waitUntil: "load" });
    const pager = page.locator(".pager").first();
    await expect(pager.locator(".pager__status")).toContainText(/Page 1 of \d+/);
    await expect(pager.locator(".pager__page--on")).toHaveText("1");
    // Present and inert rather than missing, so the row keeps its shape.
    await expect(pager.locator(".pager__disabled").first()).toHaveAttribute(
      "aria-disabled",
      "true",
    );

    await pager.getByRole("link", { name: /^Page 2 / }).click();
    await page.waitForURL(/offset=50/, { timeout: 5000 });
    await expect(page.locator(".pager__page--on").first()).toHaveText("2");
  });

  test("keeps the order across a page turn", async ({ page }) => {
    await page.goto(`${TABLE}?sort=code`, { waitUntil: "load" });
    const next = page.getByRole("link", { name: /Next/ });
    if (await next.count()) {
      await next.first().click();
      await page.waitForURL(/offset=/, { timeout: 5000 });
      expect(page.url()).toContain("sort=code");
    }
  });

  test("dismisses one filter and keeps the rest", async ({ page }) => {
    await page.goto(`${TABLE}?pl=118-42&title=42`, { waitUntil: "load" });
    await page.locator(".filterpills__clear").first().click();
    await page.waitForURL(/\/app\/classification\/118\/2\?/, { timeout: 5000 });
    expect(page.url()).not.toContain("pl=118-42");
    expect(page.url()).toContain("title=42");
  });
});

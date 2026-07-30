/**
 * The hover preview, proven in a real browser (ADR-0024).
 *
 * Vitest covers the pieces — `data-cite` emission, fragment truncation — but the
 * card itself is timers, pointer geometry, the top layer and a media query, and
 * none of that is testable without a browser. WCAG 2.1 SC 1.4.13 has three
 * clauses and each one gets a test here by name, because "dismissible,
 * hoverable, persistent" is the kind of claim that is easy to make and easy to
 * be wrong about.
 *
 * Needs the site running: `make dev-all`, then `make test-e2e`.
 */
import { expect, test } from "@playwright/test";

/** A section with cross references in its text. */
const SECTION = "/app/us/usc/t16/s45f";
const CARD = "#cite-preview";
const REF = "a[data-cite]";

/** Longer than the island's 300ms open delay, short enough to catch a hang. */
const OPENED = { timeout: 3000 };

test.describe("citation hover preview", () => {
  test("hovering a reference shows the cited provision's text", async ({ page }) => {
    await page.goto(SECTION);
    const link = page.locator(REF).first();
    const identifier = await link.getAttribute("data-cite");

    await link.hover();

    const card = page.locator(CARD);
    await expect(card).toBeVisible(OPENED);
    // Not just "a card appeared" — the card holds the section that was cited.
    await expect(card.locator(".cite-preview__foot a")).toHaveAttribute(
      "href",
      new RegExp(identifier!.replace(/\//gu, "\\/")),
    );
    await expect(card.locator(".cite-preview__head")).not.toBeEmpty();
  });

  test("SC 1.4.13 hoverable: the pointer can move onto the card", async ({ page }) => {
    // The clause most hover previews fail. Without a close delay the card
    // vanishes in the gap between the link and itself, and a scrollable preview
    // becomes unreachable.
    await page.goto(SECTION);
    await page.locator(REF).first().hover();
    const card = page.locator(CARD);
    await expect(card).toBeVisible(OPENED);

    await card.hover();
    await page.waitForTimeout(700); // well past the 250ms close delay

    await expect(card).toBeVisible();
  });

  test("SC 1.4.13 dismissible: Escape closes it without moving the pointer", async ({
    page,
  }) => {
    await page.goto(SECTION);
    await page.locator(REF).first().hover();
    await expect(page.locator(CARD)).toBeVisible(OPENED);

    await page.keyboard.press("Escape");

    await expect(page.locator(CARD)).toBeHidden();
  });

  test("SC 1.4.13 persistent: it stays while the pointer rests on the link", async ({
    page,
  }) => {
    await page.goto(SECTION);
    await page.locator(REF).first().hover();
    await expect(page.locator(CARD)).toBeVisible(OPENED);

    await page.waitForTimeout(2500);

    await expect(page.locator(CARD)).toBeVisible();
  });

  test("the card is a bounded scroll area, not an unbounded panel", async ({ page }) => {
    await page.goto(SECTION);
    await page.locator(REF).first().hover();
    const card = page.locator(CARD);
    await expect(card).toBeVisible(OPENED);

    const style = await card.evaluate((el) => {
      const cs = getComputedStyle(el);
      return {
        maxHeight: parseFloat(cs.maxHeight),
        overflowY: cs.overflowY,
        // `contain` is what stops a wheel gesture that reaches the bottom of
        // the card from scrolling the page underneath — throwing away the
        // reading position the card exists to protect.
        overscroll: cs.overscrollBehaviorY,
      };
    });

    expect(style.overflowY).toBe("auto");
    expect(style.overscroll).toBe("contain");
    expect(style.maxHeight).toBeGreaterThan(0);
    expect(style.maxHeight).toBeLessThan(600);
  });

  test("a long provision actually overflows, so the scrolling is real", async ({
    page,
  }) => {
    // Separate from the CSS contract above because this is the substantive
    // claim: the preview budget has to exceed the card's height, or the scroll
    // area is decoration. It did not, at first — 1,400 characters fitted inside
    // 22rem with room to spare, and every preview stopped mid-thought.
    await page.goto(SECTION);
    const card = page.locator(CARD);
    const links = await page.locator(REF).all();

    let sawOverflow = false;
    for (const link of links) {
      await page.mouse.move(0, 0);
      await page.waitForTimeout(120);
      await link.hover();
      await expect(card).toBeVisible(OPENED);
      const overflows = await card.evaluate((el) => el.scrollHeight > el.clientHeight + 1);
      await page.keyboard.press("Escape");
      if (overflows) {
        sawOverflow = true;
        break;
      }
    }

    expect(sawOverflow).toBe(true);
  });

  test("keyboard focus opens it too, and the card is focusable to scroll", async ({
    page,
  }) => {
    await page.goto(SECTION);
    const link = page.locator(REF).first();
    await link.focus();

    await expect(page.locator(CARD)).toBeVisible(OPENED);
    // A scrollable region with no focusable children needs a tabindex to be
    // reachable by keyboard at all.
    await expect(page.locator(CARD)).toHaveAttribute("tabindex", "0");
  });

  test("the same reference is fetched once, however often it is hovered", async ({
    page,
  }) => {
    let requests = 0;
    await page.route("**/app/preview/**", (route) => {
      requests += 1;
      return route.continue();
    });

    await page.goto(SECTION);
    const link = page.locator(REF).first();
    for (let i = 0; i < 5; i += 1) {
      // Away first: hovering an element the pointer is already over fires no
      // `mouseover`, so without this the card never reopens and the loop
      // measures nothing.
      await page.mouse.move(0, 0);
      await page.waitForTimeout(120);
      await link.hover();
      await expect(page.locator(CARD)).toBeVisible(OPENED);
      await page.keyboard.press("Escape");
    }

    expect(requests).toBe(1);
  });

  test("a failed preview costs nothing: the link still works", async ({ page }) => {
    await page.route("**/app/preview/**", (route) => route.abort());
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));

    await page.goto(SECTION);
    const link = page.locator(REF).first();
    const href = await link.getAttribute("href");
    await link.hover();
    await page.waitForTimeout(900);

    await expect(page.locator(CARD)).toBeHidden();
    expect(errors).toEqual([]);

    // The citation opens a new tab (ADR-0031), so the assertion is about the
    // popup rather than this page's URL — and this page staying put is now
    // part of the point: a preview that failed must not have cost the reader
    // the provision they were reading either.
    const [opened] = await Promise.all([page.waitForEvent("popup"), link.click()]);
    await expect(opened).toHaveURL(new RegExp(href!.split("?")[0].replace(/\//gu, "\\/")));
    await expect(page).toHaveURL(new RegExp(SECTION.replace(/\//gu, "\\/")));
  });

  test("it layers above the sticky bar and never overflows the viewport", async ({
    page,
  }) => {
    await page.goto(SECTION);
    await page.locator(REF).first().hover();
    const card = page.locator(CARD);
    await expect(card).toBeVisible(OPENED);

    const geometry = await page.evaluate(() => {
      const el = document.querySelector("#cite-preview")!.getBoundingClientRect();
      return {
        left: el.left,
        right: el.right,
        width: window.innerWidth,
        pageScrollsSideways:
          document.documentElement.scrollWidth > document.documentElement.clientWidth,
      };
    });

    expect(geometry.left).toBeGreaterThanOrEqual(0);
    expect(geometry.right).toBeLessThanOrEqual(geometry.width);
    expect(geometry.pageScrollsSideways).toBe(false);
    // `popover` renders in the top layer, which always paints above any
    // `z-index` — including the sticky bar's 500.
    await expect(card).toBeVisible();
  });
});

test.describe("citation hover preview on touch", () => {
  // Hover does not exist here, and the island is gated on
  // `(hover: hover) and (pointer: fine)`. A tap is a navigation.
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true, isMobile: true });

  test("tapping a citation navigates and no card ever appears", async ({ page }) => {
    await page.goto(SECTION);

    // Every reference in this section lives inside the notes, which render as
    // `<details>` — open on a desktop, closed on a phone (Day 4). So the mobile
    // route to a citation is: open the notes, then tap. That is the flow worth
    // testing, rather than hunting for a section that happens to differ.
    //
    // All of them, not just the first: which `<details>` holds a reference is
    // an accident of the section. A closed one gives its contents a bounding
    // box but `content-visibility: hidden`, so `:visible` correctly refuses to
    // match — which is how this was discovered rather than guessed.
    for (const summary of await page.locator(".section-body details summary").all()) {
      await summary.tap();
    }

    const link = page.locator(`${REF}:visible`).first();
    const href = await link.getAttribute("href");

    // A tap follows the link into a new tab, same as a click — the preference
    // is about where links open, not about which pointer opened them. What
    // matters on touch is the other half: no card, ever, because the island is
    // gated on `(hover: hover) and (pointer: fine)`.
    const [opened] = await Promise.all([page.waitForEvent("popup"), link.tap()]);

    await expect(opened).toHaveURL(new RegExp(href!.split("?")[0].replace(/\//gu, "\\/")));
    await expect(page.locator(CARD)).toBeHidden();
  });
});

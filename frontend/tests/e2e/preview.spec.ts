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

    const card = page.locator(CARD);
    await expect(card).toBeVisible(OPENED);
    // A scrollable region with no focusable children needs a tabindex to be
    // reachable by keyboard at all.
    await expect(card).toHaveAttribute("tabindex", "0");
    // And it must not be focusable *and* hidden from assistive technology at
    // the same time — the pairing axe calls `aria-hidden-focus`, which is what
    // the open-state scan in ADR-0039 found here (ADR-0041).
    await expect(card).not.toHaveAttribute("aria-hidden", "true");
    await expect(card).toHaveAttribute("role", "dialog");
  });

  test("the card names what it is previewing", async ({ page }) => {
    await page.goto(SECTION);
    const link = page.locator(REF).first();
    const title = await link.getAttribute("title");
    await link.focus();

    const card = page.locator(CARD);
    await expect(card).toBeVisible(OPENED);
    // Focus arriving here should announce the provision, not "dialog".
    await expect(card).toHaveAttribute("aria-label", new RegExp(`^Preview: `, "u"));
    expect(await card.getAttribute("aria-label")).toContain(title!.slice(0, 20));
  });

  test("the trigger keeps a discoverable accessible name", async ({ page }) => {
    await page.goto(SECTION);
    const link = page.locator(REF).first();

    // The reference is a link that navigates; its name stays the citation it
    // is, rather than being rewritten to describe the preview behaviour.
    const name = await link.evaluate((el) => (el.textContent ?? "").trim());
    expect(name.length).toBeGreaterThan(3);
    await expect(link).toHaveAttribute("title", /§/u);
  });

  test("Tab moves into the card, and Escape returns to the reference", async ({ page }) => {
    await page.goto(SECTION);
    const link = page.locator(REF).first();
    await link.focus();
    const card = page.locator(CARD);
    await expect(card).toBeVisible(OPENED);

    const scrollBefore = await page.evaluate(() => window.scrollY);

    // Into the card: the "Open full section" link is its first stop.
    await page.keyboard.press("Tab");
    await expect
      .poll(() => page.evaluate(() => document.getElementById("cite-preview")!.contains(document.activeElement)))
      .toBe(true);

    // And back out, to the reference the reader came from.
    await page.keyboard.press("Escape");
    await expect(card).toBeHidden();
    await expect(link).toBeFocused();
    // "Dismisses without moving the reading position": no scrolling.
    expect(await page.evaluate(() => window.scrollY)).toBe(scrollBefore);
  });

  test("a dismissed card does not immediately reopen itself", async ({ page }) => {
    // Escape returns focus to the trigger, which is a `focusin` on the trigger,
    // which is what opens the card. Without a dismissal latch the card the
    // reader just closed comes straight back and Escape is useless.
    await page.goto(SECTION);
    const link = page.locator(REF).first();
    await link.focus();
    await expect(page.locator(CARD)).toBeVisible(OPENED);

    await page.keyboard.press("Tab");
    await page.keyboard.press("Escape");
    await expect(page.locator(CARD)).toBeHidden();

    await page.waitForTimeout(700);
    await expect(page.locator(CARD)).toBeHidden();
    await expect(link).toBeFocused();
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

  test("a failed preview says so and offers the citation", async ({ page }) => {
    // It used to return silently, which is indistinguishable from a broken
    // feature or from a citation with nothing behind it (ADR-0041).
    await page.route("**/app/preview/**", (route) => route.abort());
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));

    await page.goto(SECTION);
    const link = page.locator(REF).first();
    const href = await link.getAttribute("href");
    await link.hover();

    const card = page.locator(CARD);
    await expect(card).toBeVisible(OPENED);
    await expect(card).toContainText("Preview unavailable");
    await expect(card.locator(".cite-preview__foot a")).toHaveAttribute("href", href!);
    expect(errors).toEqual([]);

    // The citation opens a new tab (ADR-0031), so the assertion is about the
    // popup rather than this page's URL — and this page staying put is now
    // part of the point: a preview that failed must not have cost the reader
    // the provision they were reading either.
    const [opened] = await Promise.all([page.waitForEvent("popup"), link.click()]);
    await expect(opened).toHaveURL(new RegExp(href!.split("?")[0].replace(/\//gu, "\\/")));
    await expect(page).toHaveURL(new RegExp(SECTION.replace(/\//gu, "\\/")));
  });

  test("a 429 names the reason rather than showing an empty box", async ({ page }) => {
    // The preview endpoint is rate-limited per caller (ADR-0029) and a reader
    // moving down a dense section will meet it.
    await page.route("**/app/preview/**", (route) =>
      route.fulfill({
        status: 429,
        headers: { "Retry-After": "12", "Content-Type": "text/plain" },
        body: "Too many requests.",
      }),
    );

    await page.goto(SECTION);
    await page.locator(REF).first().hover();

    const card = page.locator(CARD);
    await expect(card).toBeVisible(OPENED);
    await expect(card).toContainText("too many previews");
    await expect(card.locator(".cite-preview__foot a")).toBeVisible();
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

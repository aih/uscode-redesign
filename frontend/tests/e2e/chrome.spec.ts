/**
 * The site chrome, after the Session 14 rearrangement.
 *
 * Three things moved: the search page stopped rendering a second copy of the
 * search box, sign-in moved off section pages into the navbar, and the API
 * reference moved inside the site's own layout. Each of them is the kind of
 * change that a unit test cannot see, because what is being asserted is what a
 * reader finds on the page.
 */
import { expect, test } from "@playwright/test";

const BOX = ".navtools .sitesearch__input";

test("the search page shows one search box, holding the query", async ({ page }) => {
  // There used to be two: the header's, empty, and a larger copy in the page
  // body holding the query. Whichever the reader reached for first was the
  // wrong one.
  await page.goto("/app/search?q=conservation");

  await expect(page.locator("form.sitesearch")).toHaveCount(1);
  await expect(page.locator(BOX)).toHaveValue("conservation");
});

test("the syntax guide is reachable from a search that found nothing", async ({ page }) => {
  // The escape hatch for a search that is now strict (ADR-0031). If this link
  // is missing, a reader who mistyped has no way to discover `~1`.
  await page.goto("/app/search?q=zzzzqqqqxxxx");

  // Scoped to `main`: the header's explainer popover now links to the guide
  // too, and an unscoped `.first()` picks that one — which is closed, and
  // therefore hidden. What this test is about is the escape hatch on the
  // results page, so it has to say so.
  const guide = page.locator('main a[href="/app/search/syntax"]').first();
  await expect(guide).toBeVisible();
  await guide.click();
  await expect(page).toHaveURL(/\/app\/search\/syntax/);
  await expect(page.locator("h1")).toContainText("Search and citation guide");
});

test("the guide covers both halves of the one box", async ({ page }) => {
  // The box does two jobs and the guide used to document one of them, which
  // left the citation half — 84 accepted shapes — with nothing describing it.
  await page.goto("/app/search/syntax");

  await expect(page.locator("#citations")).toBeVisible();
  await expect(page.locator("#operators")).toBeVisible();
  // Each documented citation form prints the identifier it resolves to; that is
  // the claim `tests/test_citation_forms.py` checks against the real parser.
  await expect(page.locator(".syntaxop__result").first()).toContainText("/us/usc/t");
});

test("accounts are offered as coming, not as a broken door", async ({ page }) => {
  // Accounts are built and switched off (`lib/features.ts`). The failure this
  // guards against is not "no login link" — that is the intent — but a
  // greyed-out control with nothing saying why.
  await page.goto("/app/us/usc/t16/s45f");

  // Last row of the More menu (ADR-0061), which is the slot `AuthNav` takes
  // when the flag flips.
  await page.locator(".navdrop--more > summary").click();
  const trigger = page.locator(".navdrop__account .soon__trigger");
  await expect(trigger).toBeVisible();
  // Enabled, deliberately. `aria-disabled` was the first attempt and Playwright
  // refused to click it — correctly: the button is not disabled, it has an
  // action and performs it. What is unavailable is the feature it names, and
  // the label, the `title` and a visually-hidden phrase are what say so.
  await expect(trigger).toBeEnabled();
  await expect(trigger).toHaveAttribute("title", /accounts|sign in/i);

  // No door anywhere that leads to a form that cannot work.
  await expect(page.locator('.authnav a[href^="/app/login"]')).toHaveCount(0);

  await trigger.click();
  const panel = page.locator("#accounts-panel");
  await expect(panel).toBeVisible();
  await expect(panel).toContainText("alerted");
});

test("the coming-soon panel closes on Escape", async ({ page }) => {
  // It is a `popover`, so this is the platform's behaviour rather than ours —
  // asserted because it is the whole reason the control needs no JavaScript.
  await page.goto("/app/");

  await page.locator(".navdrop--more > summary").click();
  await page.locator(".navdrop__account .soon__trigger").click();
  await expect(page.locator("#accounts-panel")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator("#accounts-panel")).toBeHidden();
  // And the menu it was opened from is still open: a popover owns Escape
  // first, so the key must not close both (ADR-0061).
  await expect(page.locator(".navdrop--more")).toHaveAttribute("open", "");
});

test("a section page asks nothing of the reader", async ({ page }) => {
  await page.goto("/app/us/usc/t16/s45f");

  // With accounts off the watch island is not rendered at all, rather than
  // rendered and hidden: a hidden island still ships its script and still asks
  // `/api/v1/auth/me` who is reading, on every page, to be told nobody.
  await expect(page.getByText("Log in to track this section")).toHaveCount(0);
  await expect(page.locator(".watch-widget")).toHaveCount(0);
});

test("My Provisions explains itself rather than showing a login prompt", async ({
  page,
}) => {
  await page.goto("/app/provisions");

  await expect(page.locator("h1")).toContainText("My Provisions");
  // Scoped to `main`: the navbar's popover carries the identical heading,
  // which is the point of both reading from one constant in `lib/features.ts`.
  await expect(page.locator("main").getByText("Accounts are coming")).toBeVisible();
  // The page a bookmark lands on must not be a 404: "gone" and "not on yet"
  // are different facts.
  await expect(page.locator(".usa-alert--info")).toBeVisible();
});

test("the disabled Downloads control says what it will do", async ({ page }) => {
  await page.goto("/app/");

  await page.locator(".navdrop--more > summary").click();
  const trigger = page.locator('.navdrop__list .soon__trigger');
  await expect(trigger).toContainText("Downloads");
  // USWDS underlines and blue-links every button inside `.usa-nav__primary`,
  // which shipped this one underlined beside five links that are not.
  await expect(trigger).toHaveCSS("text-decoration-line", "none");

  await trigger.click();
  await expect(page.locator("#downloads-panel")).toContainText("bulk");
});

test("About is in the nav and carries the disclaimer", async ({ page }) => {
  await page.goto("/app/");
  await page.locator(".navdrop--more > summary").click();
  await page.locator('.navdrop a[href="/app/about"]').click();

  await expect(page).toHaveURL(/\/app\/about/);
  // The sentence that used to be eight-point grey type below the fold.
  await expect(page.locator("main")).toContainText(
    "not an official publication of the United States government",
  );
});

test.describe("the menus collapse below the desktop breakpoint (ADR-0058)", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("the navbar's links are behind a hamburger, and the hamburger opens them", async ({
    page,
  }) => {
    await page.goto("/app/");

    const list = page.locator(".usa-nav__primary");
    await expect(list).toBeHidden();

    await page.locator(".navmenu__summary").click();
    await expect(list).toBeVisible();
    await expect(page.locator('.usa-nav__primary a[href="/app/provisions"]')).toBeVisible();
    // About is in the sheet itself here, not behind More: below 64em the sheet
    // *is* the menu, so More's summary is gone and its rows are the sheet's
    // own (ADR-0064).
    await expect(page.locator(".navdrop--more > summary")).toBeHidden();
    await expect(page.locator('.navdrop a[href="/app/about"]')).toBeVisible();
  });

  test("the sheet reads Titles, My Provisions, reference, help, display", async ({
    page,
  }) => {
    // The order the mobile spec asks for, asserted as an order rather than as a
    // set: a menu is a reading sequence, and "these rows exist somewhere in
    // here" is not the claim.
    await page.goto("/app/us/usc/t16/s45f");
    await page.locator(".navmenu__summary").click();

    const rows = await page.evaluate(() => {
      const sheet = document.querySelector(".usa-nav__primary")!;
      return [
        ...sheet.querySelectorAll(
          "summary.navdrop__summary, a.usa-nav__link, a.navdrop__item, .soon__trigger, .density-toggle, .theme-toggle",
        ),
      ]
        // The Titles shortlist is behind its own disclosure and is not a row of
        // the sheet: what is a row is the `Titles` summary that opens it.
        .filter((el) => !el.closest(".navdrop--titles .navdrop__panel"))
        // More's summary is still in the markup and is `display: none` here,
        // which is the claim — so it must not count as a row.
        .filter((el) => el.getClientRects().length > 0)
        .map((el) =>
          el
            .textContent!
            // The `soon` controls carry a visually-hidden explanation, and the
            // carets and glyphs are `aria-hidden` decoration. Neither is the
            // row's name.
            .replace(/soon —.*/s, "")
            .replace(/[▾▴≡☾☀]/g, "")
            .replace(/\s+/g, " ")
            .trim(),
        );
    });

    expect(rows).toEqual([
      "Titles",
      "My Provisions",
      "Release points",
      "Classification tables",
      "Downloads",
      "User guide",
      "API docs",
      "Keyboard shortcuts ?",
      "About",
      "Compact",
      "Dark",
      "Accounts",
    ]);

    // The two dividers the spec asks for are the group labels, which name what
    // is under them rather than only separating it.
    await expect(page.locator(".navdrop--more .navdrop__group")).toHaveText([
      "Reference",
      "Help",
      "Display",
    ]);
  });

  test("every row of the bar and the sheet is a 44px target", async ({ page }) => {
    await page.goto("/app/us/usc/t16/s45f");
    await page.locator(".navmenu__summary").click();

    const short = await page.evaluate(() => {
      const bar = document.querySelector(".navbar")!;
      return [...bar.querySelectorAll("summary, a, button")]
        .filter((el) => (el as HTMLElement).offsetParent !== null)
        .map((el) => {
          const r = el.getBoundingClientRect();
          return { name: el.className || el.tagName, px: Math.min(r.width, r.height) };
        })
        .filter((t) => t.px > 0 && t.px < 44);
    });

    expect(short, "every target on the bar and in the sheet is at least 44px").toEqual([]);
  });

  test("the bar is 52px and the search box has the row under it", async ({ page }) => {
    await page.goto("/app/us/usc/t16/s45f");

    const geometry = await page.evaluate(() => {
      const round = (n: number) => Math.round(n);
      const bar = document.querySelector(".navbar")!.getBoundingClientRect();
      const tools = document.querySelector(".navtools")!.getBoundingClientRect();
      const brand = document.querySelector(".navbar__brand")!.getBoundingClientRect();
      const menu = document.querySelector(".navmenu__summary")!.getBoundingClientRect();
      const theme = document.querySelector(".navbar > .theme-toggle")!.getBoundingClientRect();
      return {
        barHeight: round(bar.height),
        searchBelowBar: round(tools.top) >= round(bar.bottom),
        // The same width as the bar above it, which is the nav's full width.
        searchFullWidth: round(tools.width) === round(bar.width),
        // Menu, then the wordmark, then the theme — left to right.
        order: [round(menu.left), round(brand.left), round(theme.left)],
      };
    });

    expect(geometry.barHeight).toBe(52);
    expect(geometry.searchBelowBar).toBe(true);
    expect(geometry.searchFullWidth).toBe(true);
    expect(geometry.order[0]).toBeLessThan(geometry.order[1]);
    expect(geometry.order[1]).toBeLessThan(geometry.order[2]);

    // And the box is on screen without opening anything, which is the whole
    // point of giving it a row: it is the control the site is built around.
    await expect(page.locator(".navtools .sitesearch__input")).toBeVisible();
  });

  test("USWDS's own bar leaves the tab order with its box", async ({ page }) => {
    // The wordmark is written twice, and a copy that is merely invisible would
    // still be a home link the keyboard reaches and the eye cannot find.
    await page.goto("/app/us/usc/t16/s45f");

    await expect(page.locator(".usa-navbar")).toBeHidden();
    await expect(page.locator(".navbar__brand a")).toBeVisible();
    // The two wordmarks, not every link to `/app/`: the Titles menu's "All
    // titles →" goes to the same place and is a different thing.
    const shown = await page
      .locator(".usa-logo a, .navbar__brand a")
      .evaluateAll((links) => links.filter((a) => a.getClientRects().length > 0).length);
    expect(shown).toBe(1);

    await page.setViewportSize({ width: 1280, height: 900 });
    await expect(page.locator(".usa-logo a")).toBeVisible();
    await expect(page.locator(".navbar__brand a")).toBeHidden();
  });

  test("opening it paints over the page rather than pushing it down", async ({ page }) => {
    // The same property `ReleasePicker` has to hold (ADR-0056): between 40em
    // and 64em this bar is sticky, and a panel in flow would be `--sticky-h`
    // growing while it happens to be open.
    await page.goto("/app/us/usc/t16/s45f");
    const top = () => page.locator("main").evaluate((el) => el.getBoundingClientRect().top);

    const closed = await top();
    await page.locator(".navmenu__summary").click();
    await expect(page.locator(".navmenu")).toHaveAttribute("open", "");
    expect(await top()).toBe(closed);
  });

  test("the footer's links are behind the same disclosure", async ({ page }) => {
    await page.goto("/app/");

    const list = page.locator(".usa-footer__nav .footnav");
    await expect(list).toBeHidden();
    // The disclaimer is not part of it: whoever arrived from a search engine
    // needs that sentence without opening anything.
    await expect(page.locator(".usa-footer__secondary-section")).toContainText(
      "Not an official publication",
    );

    await page.locator(".footmenu__summary").click();
    await expect(list).toBeVisible();
  });

  test("a More opened at desktop survives a trip through a narrow window", async ({ page }) => {
    // More is a disclosure above 64em and a group of the sheet below it
    // (ADR-0064), so a reader who opens it at desktop and then narrows the
    // window carries an `open` attribute into a band where nothing reads it.
    // The chrome's script counted it as a menu there and closed it, which is
    // invisible at 375 — its panel is forced open — and waiting for them at
    // 1280, where the menu they left open is shut.
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/app/us/usc/t16/s45f");
    await page.locator(".navdrop--more > summary").click();
    await expect(page.locator(".navdrop--more")).toHaveAttribute("open", "");

    await page.setViewportSize({ width: 375, height: 812 });
    await page.locator(".navmenu__summary").click();
    await expect(page.locator(".navmenu")).toHaveAttribute("open", "");
    // The sheet's own rows, not a menu of its own: opening the sheet leaves it
    // alone rather than reaching into it.
    await expect(page.locator(".navdrop--more")).toHaveAttribute("open", "");

    await page.setViewportSize({ width: 1280, height: 900 });
    await expect(page.locator(".navdrop--more")).toHaveAttribute("open", "");
    await expect(page.locator(".navdrop__panel--more")).toBeVisible();
  });

  test("the sheet still closes on Escape with More open inside it", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/app/us/usc/t16/s45f");
    await page.locator(".navmenu__summary").click();
    await expect(page.locator(".navmenu")).toHaveAttribute("open", "");

    await page.keyboard.press("Escape");
    await expect(page.locator(".navmenu")).not.toHaveAttribute("open", "");
    await expect(page.locator(".navmenu__summary")).toBeFocused();
  });
});

test("at desktop the menus are rows of links with no hamburger", async ({ page }) => {
  // `<details>` hides its content through `::details-content`, and this is the
  // assertion that the override forcing it visible from 64em up is in force —
  // without it the whole site navigation is a closed drawer with no handle.
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/app/");

  await expect(page.locator(".usa-nav__primary")).toBeVisible();
  await expect(page.locator(".usa-footer__nav .footnav")).toBeVisible();
  await expect(page.locator(".navmenu__summary")).toBeHidden();
  await expect(page.locator(".footmenu__summary")).toBeHidden();
});

test("the footer's eleven links are in four named groups (ADR-0063)", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/app/");

  await expect(page.locator(".footnav__label")).toHaveText([
    "Browse",
    "Learn",
    "Developers",
    "Site",
  ]);

  // The set, not the count: the regrouping is only safe if no destination was
  // dropped on the way, and `docs/ia-map.md` records the footer as the only
  // inbound link some of these have.
  const hrefs = await page.locator(".footnav a").evaluateAll((links) =>
    links.map((a) => a.getAttribute("href")),
  );
  expect(hrefs).toEqual([
    "/app/",
    "/app/releases",
    "/app/classification",
    "/app/guide",
    "/app/search/syntax",
    "/app/guide/02-reading#keyboard-shortcuts",
    "/app/docs",
    "https://uscode.house.gov/download/download.shtml",
    "/app/design",
    "/app/data/version-changes",
    "/app/about",
  ]);

  // Each label names the list under it, so the groups are navigable structure
  // rather than type set to look like it.
  await expect(page.locator('.footnav ul[aria-labelledby="footnav-browse"] a')).toHaveCount(3);
});

test("the columns stack as the window narrows", async ({ page }) => {
  // Four from 40em, two from 25em, one below it. The disclosure is closed below
  // 64em, so the columns have to be opened before they can be measured.
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/app/");
  await page.locator(".footmenu__summary").click();

  const columns = () =>
    page
      .locator(".footnav")
      .evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(" ").length);

  expect(await columns()).toBe(1);

  await page.setViewportSize({ width: 420, height: 812 });
  expect(await columns()).toBe(2);

  await page.setViewportSize({ width: 700, height: 812 });
  expect(await columns()).toBe(4);
});

/* ---------------------------------------------- the navbar's two dropdowns
 *
 * ADR-0061. The header went from eleven interactive items to four, and the two
 * that absorbed the rest are `<details>`: what they owe is an expanded state
 * assistive technology can read, and closing — Escape, an outside pointer, and
 * one at a time.
 */

test("Titles offers a shortlist and a way to all of them", async ({ page }) => {
  await page.goto("/app/us/usc/t16/s45f");

  const menu = page.locator(".navdrop--titles");
  await expect(menu.locator(".navdrop__panel")).toBeHidden();

  await menu.locator("summary").click();
  await expect(menu.locator(".navdrop__item")).not.toHaveCount(0);
  await menu.locator('a[href="/app/"]').click();
  await expect(page).toHaveURL(/\/app\/$/);
});

test("a summary carries its own expanded state", async ({ page }) => {
  // `<summary>` is exposed as a button whose expanded state is the element's
  // `open`, so nothing here keeps an `aria-expanded` attribute in sync — the
  // assertion is on what a screen reader is told, not on the markup.
  await page.goto("/app/");

  const summary = page.locator(".navdrop--more > summary");
  expect(await summary.evaluate((el) => el.ariaExpanded ?? String(el.parentElement.open))).toBe(
    "false",
  );
  await summary.click();
  expect(await summary.evaluate((el) => el.ariaExpanded ?? String(el.parentElement.open))).toBe(
    "true",
  );
});

test("only one of them is open at a time", async ({ page }) => {
  await page.goto("/app/");

  await page.locator(".navdrop--titles > summary").click();
  await expect(page.locator(".navdrop--titles")).toHaveAttribute("open", "");

  await page.locator(".navdrop--more > summary").click();
  await expect(page.locator(".navdrop--more")).toHaveAttribute("open", "");
  await expect(page.locator(".navdrop--titles")).not.toHaveAttribute("open", "");
});

test("Escape closes the open menu and gives focus back to its summary", async ({ page }) => {
  await page.goto("/app/");

  const summary = page.locator(".navdrop--more > summary");
  await summary.click();
  await expect(page.locator(".navdrop--more")).toHaveAttribute("open", "");

  await page.keyboard.press("Escape");
  await expect(page.locator(".navdrop--more")).not.toHaveAttribute("open", "");
  await expect(summary).toBeFocused();
});

test("a pointer outside closes it", async ({ page }) => {
  // A menu left open behind the reader halfway down a section is the state a
  // bare `<details>` has no way out of.
  await page.goto("/app/us/usc/t16/s45f");

  await page.locator(".navdrop--more > summary").click();
  await expect(page.locator(".navdrop--more")).toHaveAttribute("open", "");

  await page.locator("main").click({ position: { x: 5, y: 5 } });
  await expect(page.locator(".navdrop--more")).not.toHaveAttribute("open", "");
});

test("opening a menu does not push the page down", async ({ page }) => {
  // The property `ReleasePicker` and the hamburger both have to hold
  // (ADR-0056, ADR-0058): the navbar is sticky from 40em up, so a panel in flow
  // would be `--sticky-h` growing while it happens to be open.
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/app/us/usc/t16/s45f");
  const top = () => page.locator("main").evaluate((el) => el.getBoundingClientRect().top);

  const closed = await top();
  await page.locator(".navdrop--more > summary").click();
  await expect(page.locator(".navdrop--more")).toHaveAttribute("open", "");
  expect(await top()).toBe(closed);
});

test("both display switches are in the menu, and still switch", async ({ page }) => {
  await page.goto("/app/us/usc/t16/s45f");
  await page.locator(".navdrop--more > summary").click();

  const density = page.locator(".navdrop__list .density-toggle");
  const theme = page.locator(".navdrop__list .theme-toggle");
  await expect(density).toBeVisible();
  await expect(theme).toBeVisible();
  // The words are back: they were dropped below 64em to fit the chrome's row
  // (ADR-0059), and neither is on that row now.
  await expect(density).toContainText("Compact");

  await density.click();
  await expect(page.locator("html")).toHaveAttribute("data-density", "compact");
  await theme.click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("the footer and the navbar style their links the same way", async ({ page }) => {
  await page.goto("/app/");

  const footerLink = page.locator('.usa-footer__nav a[href="/app/about"]');
  await expect(footerLink).toHaveCSS("text-decoration-line", "none");
});

test("the tab mark is served and is an SVG", async ({ page, request }) => {
  await page.goto("/app/");
  await expect(page.locator('link[rel="icon"]')).toHaveAttribute(
    "href",
    "/favicon.svg",
  );

  // Root-absolute, so it is the API that answers for it rather than `/app`.
  const response = await request.get("/favicon.svg");
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("image/svg+xml");
});

test("the search input keeps its right edge", async ({ page }) => {
  // USWDS ships an unscoped `[type="search"]` rule that strips `border-right`
  // and the right radii, on the assumption the input sits flush inside
  // `.usa-search` with the submit button supplying the edge. This box is not
  // that component, so the edge simply vanished into the Go button.
  await page.goto("/app/");

  const input = page.locator(".navtools .sitesearch__input");
  await expect(input).not.toHaveCSS("border-right-width", "0px");
  await expect(input).toHaveCSS("float", "none");

  // And the text must not run under the browser's own clear button.
  const box = await input.boundingBox();
  const go = await page.locator(".sitesearch__go").boundingBox();
  expect(box!.x + box!.width).toBeLessThanOrEqual(go!.x);
});

test("the API reference renders inside the site, not as a bare Swagger page", async ({
  page,
}) => {
  await page.goto("/app/docs");

  await expect(page.locator("h1")).toContainText("API reference");
  // The whole point: the navbar and footer are there, so the reader has not
  // left the site.
  await expect(page.locator(".usa-nav__primary")).toBeVisible();
  await expect(page.locator("footer")).toBeAttached();
  // Built from `/openapi.json`, so it must actually list routes.
  expect(await page.locator(".endpoint").count()).toBeGreaterThan(5);
});

test("the header's API docs link stays inside the site", async ({ page }) => {
  await page.goto("/app/");
  await page.locator(".navdrop--more > summary").click();
  await page.locator('.navdrop a[href="/app/docs"]').click();

  await expect(page).toHaveURL(/\/app\/docs/);
});

test("cross references open in a new tab, navigation does not", async ({ page }) => {
  await page.goto("/app/us/usc/t16/s45f");

  // A citation is a departure from what you are reading, so it gets its own
  // tab; a breadcrumb *is* the reading, so it does not.
  await expect(page.locator('.section-body a[data-newtab]').first()).toHaveAttribute(
    "target",
    "_blank",
  );
  const crumb = page.locator(".usa-breadcrumb__link").first();
  await expect(crumb).not.toHaveAttribute("target", "_blank");
});

test("target=_blank never ships without rel=noopener", async ({ page }) => {
  // Without it the opened page gets a live `window.opener` handle on this one.
  await page.goto("/app/us/usc/t16/s45f");

  const unprotected = await page.evaluate(() =>
    [...document.querySelectorAll('a[target="_blank"]')].filter(
      (a) => !(a.getAttribute("rel") ?? "").includes("noopener"),
    ).length,
  );
  expect(unprotected).toBe(0);
});

/* ------------------------------------------- the "i" beside the search box
 *
 * One box does two jobs and the placeholder only shows one of them, so the
 * keyword half — and the fact that OpenSearch is underneath it, with its
 * operators available — was discoverable only by finding the guide first. The
 * guide was linked from the footer, from About and from a search that found
 * nothing: everywhere except beside the box it describes.
 */

const INFO = ".navtools .sitesearch__info";
const INFO_PANEL = "#site-q-info";

test("the search box carries an explainer naming OpenSearch", async ({ page }) => {
  await page.goto("/app/us/usc/t16/s45f");

  const trigger = page.locator(INFO);
  await expect(trigger).toBeVisible();
  // Enabled and named, for the reason `ComingSoon` is: the explanation has to
  // reach a keyboard and a screen reader, not only a pointer that hovers.
  await expect(trigger).toBeEnabled();
  await expect(trigger).toHaveAccessibleName(/keyword search/i);
  await expect(trigger).toHaveAttribute("title", /OpenSearch/);

  // It sits after the label, which is what "an (i) after the text" means when
  // the DOM order is what a screen reader follows.
  const order = await page.evaluate(() => {
    const label = document.querySelector(".navtools .sitesearch__label")!;
    const info = document.querySelector(".navtools .sitesearch__info")!;
    return label.compareDocumentPosition(info) & Node.DOCUMENT_POSITION_FOLLOWING;
  });
  expect(order).toBeTruthy();

  await trigger.click();
  const panel = page.locator(INFO_PANEL);
  await expect(panel).toBeVisible();
  await expect(panel).toContainText("OpenSearch");
  await expect(panel).toContainText("query syntax");
});

test("the explainer leads to the syntax guide", async ({ page }) => {
  await page.goto("/app/");
  await page.locator(INFO).click();

  await page.locator(`${INFO_PANEL} a[href="/app/search/syntax"]`).click();
  await expect(page).toHaveURL(/\/app\/search\/syntax/);
  await expect(page.locator("h1")).toContainText("Search and citation guide");
});

test("the explainer opens and closes without JavaScript of ours", async ({ page }) => {
  // `popover` supplies the top layer, Escape and light dismiss (ADR-0024). The
  // box itself is a plain GET form that works with scripting off (ADR-0023), so
  // explaining it must not be the thing that needs a script.
  await page.goto("/app/");

  await page.locator(INFO).click();
  await expect(page.locator(INFO_PANEL)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator(INFO_PANEL)).toBeHidden();

  // And the button must not submit the form it lives in.
  await page.locator(INFO).click();
  await expect(page).toHaveURL(/\/app\/$/);
});

test("the explainer is not inside the label, so it opens rather than focusing the input", async ({
  page,
}) => {
  // A control nested in a `<label>` gets the label's click stolen from it: the
  // input takes focus and the panel never opens.
  await page.goto("/app/");

  const nested = await page.locator(".navtools .sitesearch__label .sitesearch__info").count();
  expect(nested).toBe(0);

  await page.locator(INFO).click();
  await expect(page.locator(INFO_PANEL)).toBeVisible();
});

test("the explainer is reachable by finger as well as by mouse", async ({ page }) => {
  // The circle is 18px, which is what the label's line can afford; the target
  // is grown past it with `::after` so the hit area is honest without the
  // layout — and `--sticky-h` — growing. Asserted by clicking the corner of the
  // 44px box, which misses the circle entirely.
  await page.goto("/app/");

  const box = (await page.locator(INFO).boundingBox())!;
  await page.mouse.click(box.x - 8, box.y + box.height / 2);
  await expect(page.locator(INFO_PANEL)).toBeVisible();
});

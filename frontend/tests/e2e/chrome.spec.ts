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

  const guide = page.locator('a[href="/app/search/syntax"]').first();
  await expect(guide).toBeVisible();
  await guide.click();
  await expect(page).toHaveURL(/\/app\/search\/syntax/);
  await expect(page.locator("h1")).toContainText("Search syntax");
});

test("a logged-out reader is offered sign-in in the navbar", async ({ page }) => {
  await page.goto("/app/us/usc/t16/s45f");

  // Rendered hidden and revealed by the island once `/api/v1/auth/me` answers,
  // because the page itself is shared by every reader and cannot say who is
  // looking at it.
  await expect(page.locator('.authnav [data-role="anon"]')).toBeVisible();
  await expect(page.locator('.authnav a[href^="/app/login"]')).toBeVisible();
});

test("a section page no longer asks the reader to log in", async ({ page }) => {
  await page.goto("/app/us/usc/t16/s45f");
  await expect(page.locator('.authnav [data-role="anon"]')).toBeVisible();

  // The watch widget shows a logged-out reader nothing at all now; the door is
  // in the chrome, not in the middle of the statutory text.
  await expect(page.getByText("Log in to track this section")).toHaveCount(0);
  await expect(page.locator('.watch-widget [data-role="add"]')).toBeHidden();
  await expect(page.locator('.watch-widget [data-role="remove"]')).toBeHidden();

  // The container too, not only its contents. It reserves `min-height: 2.5rem`
  // plus a rem of margin either side so that swapping Add for Remove does not
  // shift the page — which, once the login link was removed, left an empty
  // 72px band between the status line and the first subsection for every
  // logged-out reader.
  await expect(page.locator(".watch-widget")).toBeHidden();
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
  await page.locator('.usa-nav__primary a[href="/app/docs"]').click();

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

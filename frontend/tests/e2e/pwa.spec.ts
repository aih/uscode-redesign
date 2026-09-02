/**
 * The service worker and the offline fallback (ADR-0080).
 *
 * Only a browser can answer any of this: whether registration reaches
 * `ready`, whether a navigation goes through the worker, and what a reader
 * sees when the network is gone — `context.setOffline(true)` is the whole
 * point of the file.
 *
 * Playwright contexts are ephemeral, so a worker registered here does not
 * leak into another spec — but each test still unregisters and clears the
 * caches in teardown as hygiene.
 */
import { expect, test, type BrowserContext, type Page } from "@playwright/test";

const SECTION = "/app/us/usc/t16/s45f";
const UNVISITED = "/app/us/usc/t16/s45e";

/** Registration fires on `load`; the worker then has to install, activate and
 * claim the page before a navigation goes through its fetch handler. */
async function controlled(page: Page): Promise<void> {
  await page.waitForFunction(async () => {
    await navigator.serviceWorker.ready;
    return navigator.serviceWorker.controller !== null;
  });
}

async function cleanup(page: Page, context: BrowserContext): Promise<void> {
  await context.setOffline(false);
  await page
    .evaluate(async () => {
      const registrations = await navigator.serviceWorker.getRegistrations();
      await Promise.all(registrations.map((registration) => registration.unregister()));
      const names = await caches.keys();
      await Promise.all(names.map((name) => caches.delete(name)));
    })
    .catch(() => {
      // The page may be sitting on the offline document or already closed;
      // the context is discarded either way.
    });
}

test.afterEach(async ({ page, context }) => {
  await cleanup(page, context);
});

test("the manifest and the worker are served with their content types", async ({ request }) => {
  const manifest = await request.get("/app/manifest.webmanifest");
  expect(manifest.ok()).toBe(true);
  expect(manifest.headers()["content-type"]).toMatch(/manifest\+json|application\/json/);

  const worker = await request.get("/app/sw.js");
  expect(worker.ok()).toBe(true);
  expect(worker.headers()["content-type"]).toMatch(/javascript/);
});

test("registration reaches ready with the /app/ scope", async ({ page }) => {
  await page.goto(SECTION);
  const scope = await page.evaluate(async () => (await navigator.serviceWorker.ready).scope);
  expect(new URL(scope).pathname).toBe("/app/");
});

test("a visited section renders from the cache when the network is gone", async ({
  page,
  context,
}) => {
  await page.goto(SECTION);
  await controlled(page);

  // The first navigation predates the worker, so it was never stored; this
  // one goes through the fetch handler. The store happens after the response
  // is returned, so wait for the entry rather than assuming it.
  await page.reload();
  await page.waitForFunction(async () => {
    const cache = await caches.open("usc-pages-v1");
    return (await cache.match(location.href)) !== undefined;
  });

  await context.setOffline(true);
  await page.reload();
  await expect(page.locator("h1")).toContainText("45f");
});

test("an unvisited page offline gets the offline page, listing what is stored", async ({
  page,
  context,
}) => {
  await page.goto(SECTION);
  await controlled(page);
  await page.reload();
  await page.waitForFunction(async () => {
    const cache = await caches.open("usc-pages-v1");
    return (await cache.match(location.href)) !== undefined;
  });

  await context.setOffline(true);
  await page.goto(UNVISITED);

  await expect(page.locator("h1")).toHaveText("The site is unreachable");
  // Served under the URL that failed, so the empty-href retry names it.
  expect(new URL(page.url()).pathname).toBe(UNVISITED);
  await expect(page.locator(".retry")).toBeVisible();
  // The recently-read list holds the section cached above (ADR-0041: the
  // failure surface is never nothing).
  await expect(page.locator(`#stored-pages a[href="${SECTION}"]`)).toBeVisible();
});

test("the offline page online renders normally and is not its own list entry", async ({
  page,
}) => {
  await page.goto(SECTION);
  await controlled(page);

  await page.goto("/app/offline");
  await expect(page.locator("h1")).toHaveText("The site is unreachable");
  // Never stored in the pages cache (it lives in usc-assets-v1), so the
  // recently-read list on the page itself cannot offer it.
  const stored = await page.evaluate(async () => {
    const cache = await caches.open("usc-pages-v1");
    return (await cache.keys()).map((request) => new URL(request.url).pathname);
  });
  expect(stored).not.toContain("/app/offline");
});

/**
 * What a shed request looks like when it is a page (task B6, ADR-0065).
 *
 * Its own file, and its own Playwright project, because these tests do
 * something no other test may do beside them: they empty the `/app/diff/`
 * token bucket on purpose. That bucket is global and keyed on the client
 * address (ADR-0029), every worker in this suite shares one address, and a
 * spec whose subject is a redline cannot get one while this is running. The
 * project depends on `desktop`, so it runs after everything else has finished.
 *
 * Needs the site running: `make dev-all`.
 */
import { expect, test, type Page, type Response } from "@playwright/test";

const DIFF = "/app/diff/us/usc/t16/s45f?from=119-99&to=119-102not101";

/**
 * Spend the diff bucket, then hand back.
 *
 * Bursting rather than navigating: the bucket is 20 with a token back every
 * second (ADR-0066), and rendering a diff takes long enough that a loop of
 * `page.goto` refills it about as fast as it drains. These requests cost the
 * server the same tokens and none of the rendering — `/app/diff/none` is under
 * the limited prefix, which the middleware matches before anything routes, and
 * answers 400.
 *
 * From inside the page, not through Playwright's request context: the bucket is
 * keyed on the client address, and the request context opens its own
 * connections, which need not present the browser's. In CI a burst sent through
 * it left the navigation after it answering 200 five times inside 728 ms, which
 * a refill of one token a second cannot account for. A fetch from the page under
 * test is the same caller as the navigation by construction.
 */
async function spendTheBucket(page: Page): Promise<void> {
  const shed = await page.evaluate(async () => {
    const statuses = await Promise.all(
      // Each request its own URL, and `no-store`: 60 fetches of one path are 59
      // reads of the browser's cache and one token spent.
      Array.from({ length: 60 }, (_, index) =>
        fetch(`/app/diff/none?burst=${index}`, {
          cache: "no-store",
          headers: { accept: "application/json" },
        }).then((response) => response.status),
      ),
    );
    return statuses.filter((status) => status === 429).length;
  });
  if (shed === 0) throw new Error("the diff limiter never shed a request");
}

/** Navigate to the diff and come back with the shed response. The burst leaves
 *  the bucket holding between zero and one token, so the navigation has under a
 *  second to arrive; spending again is cheaper than assuming it wins that race. */
async function gotoShed(page: Page): Promise<Response> {
  await page.goto("/app/");
  for (let attempt = 0; attempt < 5; attempt += 1) {
    await spendTheBucket(page);
    const response = await page.goto(DIFF);
    if (response?.status() === 429) return response;
  }
  throw new Error("the diff limiter shed no navigation in five attempts");
}

test.describe("the rate limiter's page (ADR-0029)", () => {
  // Serial: these share one token bucket keyed on the client address, so a
  // parallel worker spending it would make the first test's burst arrive
  // already shed.
  test.describe.configure({ mode: "serial" });

  test("a navigation that is shed gets the error page, not plain text", async ({ page }) => {
    const response = await gotoShed(page);
    expect(response.status()).toBe(429);

    await expect(page.locator(".doc-title")).toContainText("429");
    await expect(page.locator(".lede")).toContainText("rate limited");
    // The chrome the plain-text response had none of.
    await expect(page.locator("header.usa-header")).toBeVisible();
    await expect(page.locator("footer")).toBeVisible();
    // And the URL is still the one that was asked for.
    await expect(page).toHaveURL(/\/app\/diff\//u);
  });

  test("it offers the section that was being compared, which still exists", async ({ page }) => {
    // A shed request refused the work, not the provision — so unlike a 404 the
    // way back is the identifier itself.
    const response = await gotoShed(page);
    expect(response.status()).toBe(429);
    await expect(page.locator(".deadend__step--last a")).toHaveAttribute(
      "href",
      "/app/us/usc/t16/s45f",
    );
  });

  test("carries Retry-After and is never cached", async ({ request }) => {
    let response = await request.get(DIFF, { headers: { accept: "text/html" } });
    for (let i = 0; i < 80 && response.status() !== 429; i += 1) {
      response = await request.get(DIFF, { headers: { accept: "text/html" } });
    }
    expect(response.status()).toBe(429);
    expect(Number(response.headers()["retry-after"])).toBeGreaterThan(0);
    expect(response.headers()["cache-control"]).toContain("no-store");
  });

  test("a caller that did not ask for HTML still gets the text body", async ({ request }) => {
    let response = await request.get(DIFF, { headers: { accept: "application/json" } });
    for (let i = 0; i < 80 && response.status() !== 429; i += 1) {
      response = await request.get(DIFF, { headers: { accept: "application/json" } });
    }
    expect(response.status()).toBe(429);
    expect(response.headers()["content-type"]).toContain("text/plain");
    expect(await response.text()).toContain("Too many requests");
  });
});

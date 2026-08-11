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
import { expect, test } from "@playwright/test";

const DIFF = "/app/diff/us/usc/t16/s45f?from=119-99&to=119-102not101";

/**
 * Spend the diff bucket, then hand back.
 *
 * Bursting through the request context rather than by navigating: the bucket is
 * 8 with a token back every two seconds, and rendering a diff takes long enough
 * that a loop of `page.goto` refills it about as fast as it drains and never
 * reaches the limit. These requests cost the server the same tokens and none of
 * the rendering.
 */
async function spendTheBucket(context: {
  get: (url: string, options?: { headers: Record<string, string> }) => Promise<{ status(): number }>;
}): Promise<void> {
  // Comfortably more than the bucket holds (20, refilling at one a second since
  // ADR-0066): each request costs a token and takes long enough that a few come
  // back while this runs, so the loop has to outpace the refill rather than
  // merely match the capacity.
  for (let i = 0; i < 80; i += 1) {
    const response = await context.get(DIFF, { headers: { accept: "text/html" } });
    if (response.status() === 429) return;
  }
  throw new Error("the diff limiter never shed a request");
}

test.describe("the rate limiter's page (ADR-0029)", () => {
  // Serial: these share one token bucket keyed on the client address, so a
  // parallel worker spending it would make the first test's burst arrive
  // already shed.
  test.describe.configure({ mode: "serial" });

  test("a navigation that is shed gets the error page, not plain text", async ({ page }) => {
    await spendTheBucket(page.request);
    const response = await page.goto(DIFF);
    expect(response?.status()).toBe(429);

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
    await spendTheBucket(page.request);
    const response = await page.goto(DIFF);
    expect(response?.status()).toBe(429);
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

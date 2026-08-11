/**
 * What the reader gets when an address answers nothing (task B6).
 *
 * The 404 already named the release point it searched. What it did not do was
 * offer anywhere to go: "Start from the top" was the whole of it, on a site
 * where the thing the reader wanted is usually one level up. And `/app/diff/`
 * is rate limited and is a page a reader navigates to, so shedding it handed
 * back `text/plain` with no chrome at all.
 *
 * Needs the site running: `make dev-all`.
 */
import { expect, test } from "@playwright/test";

const DIFF = "/app/diff/us/usc/t16/s45f?from=119-99&to=119-102not101";

test.describe("a section that does not exist", () => {
  test("answers 404 and names the release point it searched", async ({ page }) => {
    const response = await page.goto("/app/us/usc/t16/s99999");
    expect(response?.status()).toBe(404);
    await expect(page.locator(".lede")).toContainText("nothing at /us/usc/t16/s99999");
    await expect(page.locator(".lede")).toContainText("release point");
  });

  test("offers the nearest identifier above it that does resolve", async ({ page }) => {
    await page.goto("/app/us/usc/t16/s99999");
    const last = page.locator(".deadend__step--last a");
    await expect(last).toContainText("Title 16");
    await expect(last).toHaveAttribute("href", "/app/us/usc/t16");
  });

  test("the offer is a link that works", async ({ page }) => {
    await page.goto("/app/us/usc/t16/s99999");
    await page.locator(".deadend__step--last a").click();
    await expect(page).toHaveURL(/\/app\/us\/usc\/t16$/u);
    await expect(page.locator(".doc-title")).toContainText("CONSERVATION");
  });

  test("offers nothing rather than a made-up trail when the title is not there either", async ({
    page,
  }) => {
    const response = await page.goto("/app/us/usc/t99/s1");
    expect(response?.status()).toBe(404);
    await expect(page.locator(".deadend")).toHaveCount(0);
    // The way out that needs no data is still there.
    await expect(page.locator(".deadend__else")).toBeVisible();
  });

  test("renders no second search box — there is one on the site, in the chrome", async ({
    page,
  }) => {
    await page.goto("/app/us/usc/t16/s99999");
    await expect(page.locator("#site-q")).toHaveCount(1);
    await expect(page.locator("main input[name='q']")).toHaveCount(0);
  });
});

test.describe("an appendix citation, which OLRC publishes under a different scheme", () => {
  test("explains the scheme instead of only saying not found", async ({ page }) => {
    const response = await page.goto("/app/us/usc/t5a/s3");
    expect(response?.status()).toBe(404);
    const lede = page.locator(".lede");
    await expect(lede).toContainText("Title 5 Appendix is published under the law that enacted");
    // Both real forms, which is what makes the sentence actionable.
    await expect(lede).toContainText("/us/usc/t5a/pl/92/463/s1");
    await expect(lede).toContainText("/us/usc/t50a/act/1917-05-18/ch15/s212");
  });

  test("the API says the same thing at the same identifier", async ({ request }) => {
    const response = await request.get("/api/v1/us/usc/t5a/s3");
    expect(response.status()).toBe(404);
    const body = await response.json();
    expect(body.detail).toContain("published under the law that enacted");
    expect(body.detail).toContain("/us/usc/t5a/pl/92/463/s1");
  });
});

test("a provision absent at this release point says where in time it does exist", async ({
  page,
}) => {
  // A date before the corpus starts. The identifier is real and the release is
  // not, which is the shape of gotcha 3 — an identifier can be absent at a
  // release point without being repealed — and a 404 naming only the release
  // point leaves that indistinguishable from a typo.
  const response = await page.goto("/app/us/usc/t16/s45f?date=01/01/2010");
  expect(response?.status()).toBe(404);
  await expect(page.locator(".deadend__elsewhen")).toContainText("is in the Code at");
  await expect(page.locator(".deadend__elsewhen")).toContainText("release points");
  await expect(page.locator(".deadend__elsewhen a")).toHaveAttribute(
    "href",
    "/app/versions/us/usc/t16/s45f",
  );
});

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
  for (let i = 0; i < 20; i += 1) {
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
    for (let i = 0; i < 20 && response.status() !== 429; i += 1) {
      response = await request.get(DIFF, { headers: { accept: "text/html" } });
    }
    expect(response.status()).toBe(429);
    expect(Number(response.headers()["retry-after"])).toBeGreaterThan(0);
    expect(response.headers()["cache-control"]).toContain("no-store");
  });

  test("a caller that did not ask for HTML still gets the text body", async ({ request }) => {
    let response = await request.get(DIFF, { headers: { accept: "application/json" } });
    for (let i = 0; i < 20 && response.status() !== 429; i += 1) {
      response = await request.get(DIFF, { headers: { accept: "application/json" } });
    }
    expect(response.status()).toBe(429);
    expect(response.headers()["content-type"]).toContain("text/plain");
    expect(await response.text()).toContain("Too many requests");
  });
});

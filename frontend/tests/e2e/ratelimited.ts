/**
 * Navigating to a rate-limited route from a suite that runs in parallel.
 *
 * `/app/diff/` is limited to a burst of eight refilling at one every two
 * seconds, keyed on the client address (ADR-0029). Every worker in this suite
 * shares that address, and `deadend.spec.ts` deliberately empties the bucket to
 * assert what a shed navigation looks like — so any other spec navigating to a
 * diff can arrive to a 429 through no fault of its own.
 *
 * Waiting and retrying is what the limiter asks for and what its own
 * `Retry-After` says to do. It is not a flaky-test workaround: the shed is the
 * correct response, and a spec whose subject is something else has to get past
 * it to reach that subject.
 */
import { expect, type Page, type Response } from "@playwright/test";

/** Longest a caller should ever have to wait for the diff bucket. */
const ATTEMPTS = 12;

export async function gotoDiff(page: Page, url: string): Promise<Response | null> {
  let response: Response | null = null;
  for (let attempt = 0; attempt < ATTEMPTS; attempt += 1) {
    response = await page.goto(url);
    if (response?.status() !== 429) return response;
    // The header is in seconds and is what the server says it wants.
    const after = Number(response.headers()["retry-after"] ?? 1);
    await page.waitForTimeout(Math.min(Math.max(after, 1), 5) * 1000);
  }
  expect(response?.status(), `${url} was rate limited ${ATTEMPTS} times running`).not.toBe(429);
  return response;
}

/**
 * The same wait, after a *click* has already landed on a limited route.
 *
 * `gotoDiff` cannot help there: the navigation is the click's, and by the time
 * this runs the shed page is already on screen. Reloading is what the reader
 * would do, and the URL is the one that was refused.
 */
export async function settleDiff(page: Page): Promise<void> {
  // The error page's own headline (`ErrorPage.astro`), which no diff page
  // renders. Matching on the whole `<h1>` would also match a section number.
  const shed = page.locator(".doc-title", { hasText: "429" });
  for (let attempt = 0; attempt < ATTEMPTS; attempt += 1) {
    if ((await shed.count()) === 0) return;
    await page.waitForTimeout(2000);
    await page.reload();
  }
  await expect(shed).toHaveCount(0);
}

/**
 * The site's currency in the chrome and on the front page (ADR-0085): the
 * newest release point loaded and its date under the wordmark, the same with
 * the last check in the footer, and a panel on the front page. The header is
 * the height it was at every width.
 */
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

async function newest(request: APIRequestContext): Promise<{ label: string; date: string }> {
  const status = await (await request.get("/api/v1/status")).json();
  const [year, month, day] = String(status.corpus.latest_currency_date).split("-");
  return { label: status.corpus.latest_release, date: `${month}/${day}/${year}` };
}

/** The displayed dateline, and whether each of its two parts is inside the
 *  one line it clips to. `label` replaces the release point first. */
function shownDateline(page: Page, label?: string) {
  return page.evaluate((label) => {
    const line = [...document.querySelectorAll("header .dateline")].find(
      (el) => el.getClientRects().length > 0,
    );
    if (!line) return null;
    if (label) line.querySelector(".dateline__rp")!.lastChild!.textContent = label;
    const box = line.getBoundingClientRect();
    const inside = (selector: string) => {
      const part = line.querySelector(selector)!.getBoundingClientRect();
      return part.bottom <= box.bottom + 0.5 && part.right <= box.right + 0.5;
    };
    return {
      text: line.textContent!.replace(/\s+/gu, " ").trim(),
      /** Widths of "Current", shown from 30em, and "release point", never shown. */
      currentWidth: line.querySelector(".dateline__current")!.getBoundingClientRect().width,
      rpWordWidth: line.querySelector(".dateline__rpword")!.getBoundingClientRect().width,
      through: inside(".dateline__through"),
      release: inside(".dateline__rp"),
      /** Width of "through", hidden below 22.5em. */
      throughWordWidth: line.querySelector(".dateline__word")!.getBoundingClientRect().width,
    };
  }, label);
}

for (const { width, header } of [
  { width: 320, header: 104 },
  { width: 375, header: 104 },
  { width: 700, header: 104 },
  { width: 1280, header: 73.5 },
]) {
  test(`at ${width}px the header shows the date and the release point and is ${header}px`, async ({
    page,
    request,
  }) => {
    const { label, date } = await newest(request);
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/app/us/usc/t16/s45f");

    const line = await shownDateline(page);
    expect(line).not.toBeNull();
    expect(line!.text).toBe(`Current through ${date} · release point ${label}`);
    expect(line!.through).toBe(true);
    expect(line!.release).toBe(true);
    // Read aloud in full; on screen "release point" is dropped, "Current"
    // below 30em and "through" below 22.5em.
    expect(line!.rpWordWidth).toBeLessThanOrEqual(1);
    if (width < 480) expect(line!.currentWidth).toBeLessThanOrEqual(1);
    else expect(line!.currentWidth).toBeGreaterThan(1);
    if (width < 360) expect(line!.throughWordWidth).toBeLessThanOrEqual(1);
    else expect(line!.throughWordWidth).toBeGreaterThan(1);

    // A `not` label fits as well, whichever label the corpus under test has.
    const long = await shownDateline(page, "119-102not101");
    expect(long!.through).toBe(true);
    expect(long!.release).toBe(true);

    const height = await page.locator(".usa-header").evaluate((el) => el.getBoundingClientRect().height);
    expect(Math.abs(height - header)).toBeLessThan(1);
  });
}

test("the home link is still named for the site, and a tap on the dateline goes home", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/app/us/usc/t16/s45f");

  await expect(page.locator(".navbar__brand a")).toHaveAccessibleName("United States Code");
  // Not a target of its own: the click lands on the link under it.
  const box = (await page.locator(".navbar__brand .dateline").boundingBox())!;
  await page.mouse.click(box.x + 20, box.y + box.height / 2);
  await expect(page).toHaveURL(/\/app\/$/u);
});

test("the footer states the release point and links to the list", async ({ page, request }) => {
  const { label, date } = await newest(request);
  await page.goto("/app/about");

  const line = page.locator("footer [data-site-currency]");
  await expect(line).toContainText(`Newest release point loaded: ${label}, current through ${date}.`);
  await expect(line.getByRole("link", { name: "All release points" })).toHaveAttribute(
    "href",
    "/app/releases",
  );
});

test("the front page carries the currency panel", async ({ page, request }) => {
  const { label, date } = await newest(request);
  await page.goto("/app/");

  const panel = page.getByRole("region", { name: "Site currency" });
  await expect(panel.locator(".releasebar__line")).toHaveText(
    `Newest release point loaded ${label} current through ${date}`,
  );
});

test("the design page's own chrome states no currency", async ({ page }) => {
  await page.goto("/app/design");

  await expect(page.locator("header .dateline")).toHaveCount(0);
  await expect(page.locator("footer [data-site-currency]")).toHaveCount(0);
  await expect(page.locator("main .dateline")).toHaveCount(1);
});

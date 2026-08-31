/**
 * "Compare with…" on the section header (task B5, ADR-0066).
 *
 * `/app/diff` used to be two hops from the text it compares — section, version
 * history, pick two release points. What only a browser can answer is whether
 * the control is reachable, whether its default lands on a comparison that
 * actually shows something, and whether a provision survives the trip.
 *
 * Needs the site running: `make dev-all`.
 */
import { expect, test } from "@playwright/test";

import { gotoDiff, settleDiff } from "./ratelimited";

// Not § 45f, the fixture suite's usual section: the CI corpus is Title 16 at
// 119-99 and 119-102not101 alone, and § 45f is identical at both, so its
// timeline there is one group and the control has no named default to offer.
// § 2201 is one of the two sections Pub. L. 119-102 amended between them.
const SECTION = "/app/us/usc/t16/s2201";
const PROVISION = "/app/us/usc/t16/s2201/b/1";

test.describe("the control", () => {
  test("is on the section page, closed, and opens without leaving it", async ({ page }) => {
    await page.goto(SECTION);
    const compare = page.locator(".compare");
    await expect(compare).toBeVisible();
    await expect(compare).not.toHaveAttribute("open", "");
    await expect(page.locator(".compare__panel")).toBeHidden();

    await page.locator(".compare__summary").click();
    await expect(compare).toHaveAttribute("open", "");
    await expect(page.locator(".compare__panel")).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`${SECTION}$`, "u"));
  });

  test("costs the sticky stack nothing, open or closed", async ({ page }) => {
    // It is in the page body rather than in `.contextbar`, which
    // `ReleasePicker` owns and which `--sticky-h` budgets (ADR-0056).
    await page.goto(SECTION);
    const stack = () =>
      page.locator(".topbar").evaluate((el) => el.getBoundingClientRect().height);

    const closed = await stack();
    await page.locator(".compare__summary").click();
    await expect(page.locator(".compare__panel")).toBeVisible();
    expect(await stack()).toBe(closed);
  });

  test("defaults to the last release point holding different statutory text", async ({
    page,
    request,
  }) => {
    await page.goto(SECTION);
    await page.locator(".compare__summary").click();

    const href = await page.locator(".compare__go").getAttribute("href");
    const from = new URL(href!, "http://localhost").searchParams.get("from");

    // The same answer the timeline gives, computed from the other end: back
    // through the groups whose arrival changed no statutory text (ADR-0075),
    // then the last release point of the group before that one.
    const versions = await (
      await request.get("/api/v1/sections/us/usc/t16/s2201/versions")
    ).json();
    const groups = versions.versions;
    let changed = groups.length - 1;
    while (
      changed > 0 &&
      groups[changed].change_kind != null &&
      groups[changed].change_kind !== "text" &&
      groups[changed].change_kind !== "initial"
    ) {
      changed -= 1;
    }
    expect(changed).toBeGreaterThan(0);
    const expected = groups[changed - 1].releases.slice(-1)[0];
    expect(from).toBe(expected);
  });

  test("names a public law for the amendment it offers", async ({ page, request }) => {
    // The other end of the same annotation: the transition the default lands on
    // is one the classification tables attribute to Pub. L. 119-102 (ADR-0074).
    const versions = await (
      await request.get("/api/v1/sections/us/usc/t16/s2201/versions")
    ).json();
    const newest = versions.versions[versions.versions.length - 1];
    expect(newest.change_kind).toBe("text");
    expect(newest.attribution).toBe("classified");
    expect(newest.laws.map((law: { pl_num: number }) => law.pl_num)).toContain(102);

    await page.goto("/app/versions/us/usc/t16/s2201");
    await expect(page.locator(".timeline__law").last()).toContainText("Pub. L. 119–102");
  });

  test("the default is one click, and the comparison it reaches is not empty", async ({
    page,
  }) => {
    await page.goto(SECTION);
    await page.locator(".compare__summary").click();
    await page.locator(".compare__go").click();
    await settleDiff(page);

    await expect(page).toHaveURL(/\/app\/diff\/us\/usc\/t16\/s2201\?from=/u);
    // The point of choosing the previous *changed* release rather than the
    // previous release point: this redline says something.
    await expect(page.locator(".diff-verdict")).not.toContainText("No changes");
  });

  test("the select offers only older release points", async ({ page }) => {
    await page.goto(SECTION);
    await page.locator(".compare__summary").click();

    const current = await page.locator(".contextbar__rp, .rpswitch__rp").first().innerText();
    const options = await page.locator("#compare-from option").allInnerTexts();
    expect(options.length).toBeGreaterThan(0);
    expect(options.some((option) => option.startsWith(current.trim()))).toBe(false);
  });

  test("the form is a GET, so what it produces is a URL", async ({ page }) => {
    await page.goto(SECTION);
    await page.locator(".compare__summary").click();
    // Index 0, not 1: the CI corpus holds exactly one older release point.
    await page.selectOption("#compare-from", { index: 0 });
    await page.locator(".compare__submit").click();

    await expect(page).toHaveURL(/\/app\/diff\/us\/usc\/t16\/s2201\?.*from=/u);
    await expect(page).toHaveURL(/to=/u);
  });
});

test.describe("a provision keeps its place", () => {
  test("the default link carries the subsection", async ({ page }) => {
    // ADR-0044 found the release switcher dropping the provision. Same shape,
    // different control.
    await page.goto(PROVISION);
    await page.locator(".compare__summary").click();
    const href = await page.locator(".compare__go").getAttribute("href");
    expect(new URL(href!, "http://localhost").searchParams.get("at")).toBe("/b/1");
  });

  test("the form carries it too", async ({ page }) => {
    await page.goto(PROVISION);
    await page.locator(".compare__summary").click();
    await expect(page.locator(".compare__form input[name='at']")).toHaveAttribute(
      "value",
      "/b/1",
    );
  });

  test("the comparison marks it inside the whole section's redline", async ({ page }) => {
    await page.goto(PROVISION);
    await page.locator(".compare__summary").click();
    await page.locator(".compare__go").click();
    await settleDiff(page);

    // The whole section, per ADR-0001 — and the part that was asked about,
    // named before the redline rather than left to be found in it.
    await expect(page.locator(".diff-focusnote")).toContainText("(b)(1)");
    await expect(page.locator("#diff-focus")).toHaveCount(1);
    await expect(page.locator(".diff-line--focus").first()).toBeVisible();
    // Context is still there: more lines than the marked ones.
    const all = await page.locator(".diff-line").count();
    const marked = await page.locator(".diff-line--focus").count();
    expect(all).toBeGreaterThan(marked);
  });

  test("the jump link reaches the marked provision", async ({ page }) => {
    await page.goto(PROVISION);
    await page.locator(".compare__summary").click();
    await page.locator(".compare__go").click();
    await settleDiff(page);
    await page.locator('.diff-focusnote a[href="#diff-focus"]').click();
    await expect(page).toHaveURL(/#diff-focus$/u);
    await expect(page.locator("#diff-focus")).toBeInViewport();
  });

  test("a provision that is in neither text says so rather than marking nothing", async ({
    page,
  }) => {
    await gotoDiff(page, "/app/diff/us/usc/t16/s45f?from=119-99&to=119-102not101&at=/z/9");
    await expect(page.locator(".diff-focusnote")).toContainText("no (z)(9)");
    await expect(page.locator(".diff-line--focus")).toHaveCount(0);
  });
});

test("a comparison without ?at= marks nothing and says nothing", async ({ page }) => {
  await gotoDiff(page, "/app/diff/us/usc/t16/s45f?from=119-99&to=119-102not101");
  await expect(page.locator(".diff-focusnote")).toHaveCount(0);
  await expect(page.locator(".diff-line--focus")).toHaveCount(0);
});

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

const SECTION = "/app/us/usc/t16/s45f";
const PROVISION = "/app/us/usc/t16/s45f/c/5";

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

  test("defaults to the last release point holding different text", async ({ page, request }) => {
    await page.goto(SECTION);
    await page.locator(".compare__summary").click();

    const href = await page.locator(".compare__go").getAttribute("href");
    const from = new URL(href!, "http://localhost").searchParams.get("from");

    // The same answer the timeline gives, computed from the other end: the last
    // release point of the group before the one holding the text on screen.
    const versions = await (
      await request.get("/api/v1/sections/us/usc/t16/s45f/versions")
    ).json();
    const groups = versions.versions;
    const expected = groups[groups.length - 2].releases.slice(-1)[0];
    expect(from).toBe(expected);
  });

  test("the default is one click, and the comparison it reaches is not empty", async ({
    page,
  }) => {
    await page.goto(SECTION);
    await page.locator(".compare__summary").click();
    await page.locator(".compare__go").click();
    await settleDiff(page);

    await expect(page).toHaveURL(/\/app\/diff\/us\/usc\/t16\/s45f\?from=/u);
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
    await page.selectOption("#compare-from", { index: 1 });
    await page.locator(".compare__submit").click();

    await expect(page).toHaveURL(/\/app\/diff\/us\/usc\/t16\/s45f\?.*from=/u);
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
    expect(new URL(href!, "http://localhost").searchParams.get("at")).toBe("/c/5");
  });

  test("the form carries it too", async ({ page }) => {
    await page.goto(PROVISION);
    await page.locator(".compare__summary").click();
    await expect(page.locator(".compare__form input[name='at']")).toHaveAttribute(
      "value",
      "/c/5",
    );
  });

  test("the comparison marks it inside the whole section's redline", async ({ page }) => {
    await page.goto(PROVISION);
    await page.locator(".compare__summary").click();
    await page.locator(".compare__go").click();
    await settleDiff(page);

    // The whole section, per ADR-0001 — and the part that was asked about,
    // named before the redline rather than left to be found in it.
    await expect(page.locator(".diff-focusnote")).toContainText("(c)(5)");
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

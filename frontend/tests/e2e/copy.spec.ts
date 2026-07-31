/**
 * The copy column (`CopyColumn.astro`).
 *
 * Vitest covers the part that is a pure function — `formatCitation`, in
 * `tests/cite.test.ts` — and cannot cover any of this: the clipboard is a
 * browser capability, the buttons are injected into the document after it
 * loads, and the modifier keys are real key state rather than a flag someone
 * can pass.
 *
 * The bug this file exists to catch first is the one the widget shipped with
 * for a build: the island is rendered *above* the statutory text, so at the
 * moment an inline script runs, `.section-body` and every provision it is
 * looking for are still unparsed. The guard did its job, nothing threw, nothing
 * appeared in the console, and the feature silently did not exist. Every
 * assertion below that counts buttons is an assertion about that.
 */
import { expect, test, type Locator, type Page } from "@playwright/test";

const SECTION = "/app/us/usc/t16/s45f";

test.use({ permissions: ["clipboard-read", "clipboard-write"] });

function clipboard(page: Page): Promise<string> {
  return page.evaluate(() => navigator.clipboard.readText());
}

/** What each mode announces when it has finished writing. */
const ANNOUNCED = {
  text: "Text copied",
  citation: "Citation copied",
  both: "Citation and text copied",
  link: "Link copied",
} as const;

/**
 * Click a control, wait for it to finish, and read what it wrote.
 *
 * The waiting is the point. `click()` returns once the click is dispatched,
 * and the handler writes the clipboard in a promise nothing on this side
 * awaits — so reading immediately is a race, and **link mode loses it**: a
 * `ClipboardItem` carrying two blobs takes measurably longer to resolve than
 * `writeText`, so the read came back with the *previous* mode's text while the
 * page went on to say "Link copied" a moment later. It failed only on CI,
 * where one worker on a slower machine widened the gap; the widget was working
 * the whole time.
 *
 * The status line is the page's own signal that the write resolved, and each
 * mode's wording is distinct, so this waits for the exact event rather than
 * sleeping and hoping. Every clipboard read in this file goes through it.
 */
async function copyWith(
  page: Page,
  button: Locator,
  mode: keyof typeof ANNOUNCED,
  options?: Parameters<Locator["click"]>[0],
): Promise<string> {
  await button.click(options);
  await expect(page.locator("[data-copy-status]")).toHaveText(ANNOUNCED[mode]);
  return clipboard(page);
}

test("a control appears beside every provision", async ({ page }) => {
  await page.goto(SECTION);

  const buttons = page.locator(".copybtn");
  await expect(buttons.first()).toBeVisible();
  expect(await buttons.count()).toBeGreaterThan(5);

  // The gutter is opened by the island, not by the server: a reader with
  // scripting off keeps the full reading measure rather than a strip reserved
  // for controls that never arrive.
  await expect(page.locator(".section-body.has-copy")).toHaveCount(1);
});

test("the section itself is a named button, not a gutter icon", async ({ page }) => {
  await page.goto(SECTION);

  // In the gutter it would land on the same line as the first subsection's —
  // two identical icons an inch apart, one copying six words and the other
  // twelve thousand.
  const whole = page.locator("[data-copy-whole]");
  await expect(whole).toContainText("Whole section");

  const text = await copyWith(page, whole, "text");
  expect(text).toContain("Mineral King Valley");
  expect(text.length).toBeGreaterThan(2000);
});

test("each mode copies what it says it copies", async ({ page }) => {
  await page.goto(SECTION);
  const button = page.locator(".copybtn").nth(1);

  await page.selectOption("[data-copy-mode]", "citation");
  const cite = await copyWith(page, button, "citation");
  expect(cite).toMatch(/^16 U\.S\.C\. § 45f\([a-z0-9]+\)/u);

  await page.selectOption("[data-copy-mode]", "text");
  const text = await copyWith(page, button, "text");
  expect(text).not.toContain("U.S.C.");
  expect(text.length).toBeGreaterThan(20);

  await page.selectOption("[data-copy-mode]", "both");
  expect(await copyWith(page, button, "both")).toBe(`${cite}\n\n${text}`);

  await page.selectOption("[data-copy-mode]", "link");
  const link = await copyWith(page, button, "link");
  expect(link).toContain("/app/us/usc/t16/s45f/");
  // The release point travels with it, so the URL names the text the reader was
  // actually looking at rather than whatever is current when it is opened.
  expect(link).toContain("release=");
});

test("a modifier key overrides the toggle for one click only", async ({ page }) => {
  await page.goto(SECTION);
  await page.selectOption("[data-copy-mode]", "text");
  const button = page.locator(".copybtn").nth(1);

  const shifted = await copyWith(page, button, "citation", { modifiers: ["Shift"] });
  expect(shifted).toContain("U.S.C. §");

  // The toggle is what the reader set; the modifier is the exception they made
  // just now. Writing it back to storage would silently redefine "set".
  await expect(page.locator("[data-copy-mode]")).toHaveValue("text");
  expect(await copyWith(page, button, "text")).not.toContain("U.S.C. §");
});

test("the chosen mode survives a navigation", async ({ page }) => {
  await page.goto(SECTION);
  await page.selectOption("[data-copy-mode]", "citation");

  await page.goto("/app/us/usc/t16/s45e");
  await expect(page.locator("[data-copy-mode]")).toHaveValue("citation");
});

test("copied text leaves out the notes and the source credit", async ({ page }) => {
  await page.goto(SECTION);
  await page.selectOption("[data-copy-mode]", "text");
  const text = await copyWith(page, page.locator("[data-copy-whole]"), "text");

  // The section's apparatus is about the provision rather than part of it; a
  // reader pasting into a brief does not want the amendment history under it.
  const credit = await page.locator(".uslm-sourceCredit").first().innerText();
  const firstLine = credit.split("\n").filter(Boolean).pop();
  if (firstLine && firstLine.length > 25) {
    expect(text).not.toContain(firstLine.slice(0, 25));
  }
});

test("a designator and its sentence stay on one line", async ({ page }) => {
  // `<content>` renders as a `<p>`, so a naive block rule puts a break between
  // `(1)` and the words it numbers — and the Code prints them together.
  await page.goto(SECTION);
  await page.selectOption("[data-copy-mode]", "text");
  const text = await copyWith(page, page.locator("[data-copy-whole]"), "text");

  expect(text).toMatch(/\([a-z0-9]+\) \S/u);
});

test("copying announces itself", async ({ page }) => {
  await page.goto(SECTION);
  await page.selectOption("[data-copy-mode]", "citation");
  await page.locator(".copybtn").nth(1).click();

  // A live region, because the button may be a screenful below the status line.
  await expect(page.locator("[data-copy-status]")).toHaveText("Citation copied");
});

test("every control names the provision it copies", async ({ page }) => {
  await page.goto(SECTION);

  // "Copy, button" announced a hundred times says nothing. The label is the
  // citation, which is the only thing that distinguishes one from the next.
  const label = await page.locator(".copybtn").nth(1).getAttribute("aria-label");
  expect(label).toMatch(/^Copy 16 U\.S\.C\. §/u);
});

test("a table of contents gets no copy column", async ({ page }) => {
  // There is no statutory text on it to copy, and the toggle would govern
  // nothing.
  await page.goto("/app/us/usc/t16/ch1");

  await expect(page.locator("[data-copycol]")).toHaveCount(0);
  await expect(page.locator(".copybtn")).toHaveCount(0);
});

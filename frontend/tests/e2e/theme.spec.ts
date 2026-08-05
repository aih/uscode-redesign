/**
 * Light by default, dark by choice (ADR-0027).
 *
 * Every test here runs with the *operating system* set to dark, because that
 * is precisely the case the old `prefers-color-scheme` rule got wrong: a
 * reader whose laptop is dark was handed the United States Code light-on-black
 * without ever asking for it.
 *
 * Only a browser can answer any of this — the media query, `localStorage`, and
 * whether the choice survives a navigation are not things a unit test sees.
 */
import { expect, test, type Page } from "@playwright/test";

const PAGE = "/app/us/usc/t16/s45f";
const TOGGLE = "[data-theme-toggle]";

test.use({ colorScheme: "dark" });

/**
 * The page's background, and the `--page` token it is supposed to come from.
 *
 * Compared against each other rather than against a literal colour. What this
 * file is about is which theme is in force, not what the palette happens to be
 * — and a hard-coded `rgb(255, 255, 255)` here failed the day the brand landed
 * (ADR-0052) without anything about the theming having changed.
 */
async function background(page: Page): Promise<{ body: string; token: string }> {
  return page.evaluate(() => {
    const probe = document.createElement("div");
    probe.style.color = getComputedStyle(document.documentElement).getPropertyValue("--page");
    document.body.append(probe);
    const token = getComputedStyle(probe).color;
    probe.remove();
    return { body: getComputedStyle(document.body).backgroundColor, token };
  });
}

test("the site is light even when the OS asks for dark", async ({ page }) => {
  await page.goto(PAGE);

  await expect(page.locator("html")).not.toHaveAttribute("data-theme", "dark");
  const light = await background(page);
  expect(light.body).toBe(light.token);
});

test("the toggle switches to dark and back", async ({ page }) => {
  await page.goto(PAGE);
  const toggle = page.locator(TOGGLE);

  // Hidden until the script that makes it work has run: a dead control in the
  // chrome would be worse than none.
  await expect(toggle).toBeVisible();
  await expect(toggle).toHaveAccessibleName("Switch to dark mode");

  const before = await background(page);

  await toggle.click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const dark = await background(page);
  expect(dark.body).toBe(dark.token);
  expect(dark.body).not.toBe(before.body);
  await expect(toggle).toHaveAccessibleName("Switch to light mode");

  await toggle.click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  const after = await background(page);
  expect(after.body).toBe(after.token);
  expect(after.body).toBe(before.body);
});

test("the choice survives a navigation, and lands before the first paint", async ({ page }) => {
  await page.goto(PAGE);
  await page.locator(TOGGLE).click();

  await page.goto("/app/releases");

  // Not just "eventually dark": the attribute must be on `<html>` from the
  // document's own head script, or every navigation flashes white first.
  const stampedInHead = await page.evaluate(() => {
    const script = document.head.querySelector("script");
    return script?.textContent?.includes("usc-theme") ?? false;
  });
  expect(stampedInHead).toBe(true);
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("the toggle costs the sticky chrome no height", async ({ page }) => {
  // `--sticky-h` is what `scroll-margin-top` spends (see sticky.spec.ts). A
  // control added to the navbar that wrapped onto its own row would push the
  // stack past the token and send deep links behind the bar.
  await page.setViewportSize({ width: 700, height: 900 });
  await page.goto(PAGE);

  const { topbar, token } = await page.evaluate(() => {
    const bar = document.querySelector(".topbar") as HTMLElement;
    const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
    const declared = getComputedStyle(document.documentElement).getPropertyValue("--sticky-h");
    return { topbar: bar.getBoundingClientRect().height, token: parseFloat(declared) * rem };
  });

  expect(topbar).toBeLessThanOrEqual(token);
});

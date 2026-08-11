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
/** There are two of these buttons (ADR-0064) — one on the mobile bar and one in
 * the More menu — and exactly one of them is displayed at any width, so a
 * selector that names neither matches both and Playwright refuses it. These
 * tests run at the project's desktop viewport, where the menu's is the live
 * one. */
const TOGGLE = ".navdrop__list .theme-toggle";
const BAR_TOGGLE = ".navbar > .theme-toggle";
/** The control is a row of the navbar's More menu (ADR-0061). */
const MORE = ".navdrop--more > summary";

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
  await page.locator(MORE).click();
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
  await page.locator(MORE).click();
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

/* ------------------------------------------- two buttons, one setting (ADR-0064)
 *
 * The theme is a row of the More menu at desktop and a control on the bar below
 * 64em, which is two `<button>` elements for one setting. What that owes: one
 * of them displayed at a time, both bound, and the hidden one already correct
 * when a resize reveals it.
 */

test("the bar carries the theme below the desktop breakpoint, and the menu above it", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(PAGE);
  await expect(page.locator(BAR_TOGGLE)).toBeVisible();
  // Present but not displayed, so there is one theme control in the tab order
  // and one in the accessibility tree.
  await expect(page.locator(TOGGLE)).toBeHidden();

  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(page.locator(BAR_TOGGLE)).toBeHidden();
  await page.locator(MORE).click();
  await expect(page.locator(TOGGLE)).toBeVisible();
});

test("the bar's toggle switches, and is one tap from the page", async ({ page }) => {
  // One tap, where ADR-0061 left it two: open More, then click. That is the
  // whole of what B9 buys on a phone.
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(PAGE);

  const bar = page.locator(BAR_TOGGLE);
  await expect(bar).toHaveAccessibleName("Switch to dark mode");
  await bar.click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(bar).toHaveAccessibleName("Switch to light mode");
});

test("the copy that is not on screen is painted too", async ({ page }) => {
  // The script binds every `[data-theme-toggle]` and paints all of them. If it
  // painted only the visible one, a reader who switched on a phone and then
  // widened the window would find a menu row offering to switch to the mode
  // they are already in.
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(PAGE);
  await page.locator(BAR_TOGGLE).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.locator(MORE).click();
  await expect(page.locator(TOGGLE)).toHaveAccessibleName("Switch to light mode");
  await expect(page.locator(`${TOGGLE} .theme-toggle__label`)).toHaveText("Light");
});

test("the island's script ships once", async ({ page }) => {
  // Two copies would bind every button twice, and a click would toggle the
  // theme and toggle it back. The button that carries the script has to be the
  // last of the two in the document, so `script={false}` is on the other.
  await page.goto(PAGE);

  const copies = await page.evaluate(
    () =>
      [...document.querySelectorAll("script")].filter((s) =>
        s.textContent?.includes("usc-theme"),
      ).length,
  );
  // One island, plus `Base`'s pre-paint bootstrap, which reads the same key.
  expect(copies).toBe(2);
});

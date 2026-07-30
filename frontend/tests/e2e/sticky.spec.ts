/**
 * The sticky reading chrome, and the one number that keeps it honest.
 *
 * `--sticky-h` is a hand-maintained constant that has to stay at least as large
 * as whatever actually sticks, because it is what `scroll-margin-top` spends.
 * It has already drifted twice in one session — once when the section bar was
 * added, once when the citation box was — and each time the symptom was the
 * same: a deep-linked provision rendering *behind* the bar. Nobody is going to
 * remember to re-measure. This does.
 */
import { expect, test } from "@playwright/test";

const SECTION = "/app/us/usc/t16/s45f";
const DEEP_LINK = "/app/us/usc/t16/s45f/c/5?date=07/12/2026";
const BAR = ".sectionbar";

/** The widths that behave differently: a phone (only the section bar sticks),
 * the band where USWDS's nav is still a wrapping row, and true desktop. */
const WIDTHS = [
  { name: "phone", width: 375, height: 812 },
  { name: "wrapping nav", width: 700, height: 900 },
  { name: "desktop", width: 1280, height: 900 },
];

for (const size of WIDTHS) {
  test.describe(`at ${size.name} (${size.width}px)`, () => {
    test.use({ viewport: { width: size.width, height: size.height } });

    test("the section bar survives a long scroll, and still names the section", async ({
      page,
    }) => {
      await page.goto(SECTION);
      await page.evaluate(() => window.scrollTo(0, 3000));
      await page.waitForTimeout(300);

      const bar = page.locator(BAR);
      await expect(bar).toBeVisible();
      await expect(bar.locator(".sectionbar__num")).toHaveText("§ 45f");

      // Visible is not enough — it has to be pinned, not merely on screen
      // because the page happens to be short. Checked against `--sticky-h`
      // rather than a magic number, which makes this the test that catches the
      // token drifting behind the chrome: the stack must fit in what the token
      // claims, because that claim is what `scroll-margin-top` spends.
      const geometry = await page.evaluate(() => {
        const box = document.querySelector(".sectionbar")!.getBoundingClientRect();
        const token = getComputedStyle(document.documentElement).getPropertyValue(
          "--sticky-h",
        );
        return {
          top: box.top,
          bottom: box.bottom,
          stickyH: parseFloat(token) * 16, // the token is in rem
        };
      });

      expect(geometry.top).toBeGreaterThanOrEqual(0);
      expect(geometry.bottom).toBeLessThanOrEqual(geometry.stickyH);
    });

    test("a deep-linked provision is not hidden behind the bar", async ({ page }) => {
      await page.goto(DEEP_LINK);
      await page.waitForTimeout(700); // the page's own scrollIntoView

      const geometry = await page.evaluate(() => {
        const target = document.querySelector(".target")!.getBoundingClientRect();
        const bar = document.querySelector(".sectionbar")!.getBoundingClientRect();
        return { targetTop: target.top, barBottom: bar.bottom };
      });

      expect(geometry.targetTop).toBeGreaterThanOrEqual(geometry.barBottom);
    });

    test("an in-page anchor jump clears the bar too", async ({ page }) => {
      // The case `scroll-margin-top` exists for, and the one the page's own
      // `scrollIntoView({block:"center"})` does *not* mask.
      await page.goto(SECTION);
      const jumped = await page.evaluate(() => {
        const elements = document.querySelectorAll(".section-body [id]");
        const last = elements[elements.length - 1] as HTMLElement | undefined;
        if (!last) return null;
        location.hash = last.id;
        return last.id;
      });
      expect(jumped).not.toBeNull();
      await page.waitForTimeout(400);

      const geometry = await page.evaluate((id: string) => {
        const el = document.getElementById(id)!.getBoundingClientRect();
        const bar = document.querySelector(".sectionbar")!.getBoundingClientRect();
        return { top: el.top, barBottom: bar.bottom };
      }, jumped!);

      expect(geometry.top).toBeGreaterThanOrEqual(geometry.barBottom);
    });

    test("nothing scrolls sideways", async ({ page }) => {
      await page.goto(DEEP_LINK);
      const sideways = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
      );
      expect(sideways).toBe(false);
    });
  });
}

test.describe("what sticks at each width", () => {
  test("a phone pins only the section bar", async ({ page }) => {
    // The whole stack would be ~280px of a 660px viewport — reading statutory
    // law through a slot.
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(SECTION);
    await page.evaluate(() => window.scrollTo(0, 2000));
    await page.waitForTimeout(300);

    const header = await page.locator(".usa-header").evaluate((el) => {
      const box = el.getBoundingClientRect();
      return { bottom: box.bottom };
    });
    // The navbar has scrolled away…
    expect(header.bottom).toBeLessThan(0);
    // …and the bar has not.
    await expect(page.locator(BAR)).toBeInViewport();
  });

  test("a desktop keeps the navbar, the breadcrumbs and the bar", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(SECTION);
    await page.evaluate(() => window.scrollTo(0, 2000));
    await page.waitForTimeout(300);

    await expect(page.locator(".usa-header")).toBeInViewport();
    await expect(page.locator(".usa-breadcrumb")).toBeInViewport();
    await expect(page.locator(".picker")).toBeInViewport();
    await expect(page.locator(BAR)).toBeInViewport();
  });
});

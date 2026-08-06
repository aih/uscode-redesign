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

test.describe("the search box's explainer costs the chrome nothing", () => {
  /**
   * The "i" beside the search label is 18px in a 13px line, so on its own it
   * made every sticky stack from 640px up 5px taller — measured, not assumed.
   * A negative block margin takes that back out of the outer height.
   *
   * This asserts the *difference* rather than a number, by removing the button
   * from the layout on the same page and re-measuring: an absolute figure would
   * only re-state what the assertions above already check against the token,
   * and would drift with every other change to the chrome. The delta is the
   * thing this control owes.
   */
  for (const size of WIDTHS) {
    test(`at ${size.name} (${size.width}px) the stack is the same height with and without it`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await page.goto(SECTION);
      await page.evaluate(() => window.scrollTo(0, 3000));
      await page.waitForTimeout(300);

      const measure = () =>
        page.evaluate(() => {
          let bottom = 0;
          for (const element of document.querySelectorAll("body *")) {
            const style = getComputedStyle(element);
            if (style.position !== "sticky" && style.position !== "fixed") continue;
            // The rail pins beside the text (ADR-0050) and runs to the foot of
            // the viewport. Left in, it is the tallest thing here and both
            // measurements below become its height — equal, and measuring
            // nothing.
            if (element.closest(".rail")) continue;
            const box = element.getBoundingClientRect();
            // `top < 400` keeps this to the chrome at the top of the viewport
            // rather than anything pinned elsewhere on the page.
            if (box.height > 0 && box.top < 400 && box.bottom > bottom) bottom = box.bottom;
          }
          return Math.round(bottom);
        });

      const withInfo = await measure();
      await page.evaluate(() => {
        (document.querySelector(".sitesearch__info") as HTMLElement).style.display = "none";
      });
      await page.waitForTimeout(200);
      const withoutInfo = await measure();

      expect(withInfo).toBe(withoutInfo);
    });
  }
});

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

  test("a desktop keeps the navbar, the breadcrumbs, the release point and the bar", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(SECTION);
    await page.evaluate(() => window.scrollTo(0, 2000));
    await page.waitForTimeout(300);

    await expect(page.locator(".usa-header")).toBeInViewport();
    await expect(page.locator(".usa-breadcrumb")).toBeInViewport();
    // The release point — the answer to "as of when", and now also the control
    // that changes it. The switcher's closed summary carries the same words the
    // plain `<p>` here used to, which is what let it back into the stack: the
    // date field that pushed it out in ADR-0044 is in a panel that is only laid
    // out when the disclosure is open, and out of flow when it is.
    await expect(page.locator(".rpswitch__summary")).toBeInViewport();
    await expect(page.locator(".rpswitch__rp")).toContainText("119-102not101");
    await expect(page.locator(BAR)).toBeInViewport();
  });
});

test.describe("what the chrome costs", () => {
  /**
   * `--sticky-h` is what `scroll-margin-top` spends, so every rem the chrome
   * takes is a rem of the viewport a deep-linked provision starts below. The
   * release switcher is back in this stack as a `<details>`, and this is the
   * assertion that says it was free: its closed summary is one line where the
   * release point was already one line, and the panel that holds the date field
   * is `position: absolute`, so opening it moves nothing.
   *
   * Asserted as headroom rather than as a number: the point is that the stack
   * fits inside the token with room to spare, and a future addition that eats
   * all of it should have to argue for raising the token deliberately.
   */
  for (const size of [
    { name: "wrapping nav", width: 700, height: 900, headroom: 60 },
    { name: "desktop", width: 1280, height: 900, headroom: 60 },
  ]) {
    test(`at ${size.name} (${size.width}px) the chrome leaves ${size.headroom}px spare`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await page.goto(SECTION);
      await page.evaluate(() => window.scrollTo(0, 3000));
      await page.waitForTimeout(300);

      const spare = await page.evaluate(() => {
        let bottom = 0;
        for (const element of document.querySelectorAll("body *")) {
          const style = getComputedStyle(element);
          if (style.position !== "sticky" && style.position !== "fixed") continue;
          // The rail sticks beside the text rather than above it (ADR-0050), so
          // it costs an anchor jump nothing and must not be measured as though
          // it did. It pins at `--sticky-h` and runs to the foot of the
          // viewport, which without this reads as several hundred pixels of
          // chrome over budget.
          if (element.closest(".rail")) continue;
          const box = element.getBoundingClientRect();
          if (box.height > 0 && box.top < 400 && box.bottom > bottom) bottom = box.bottom;
        }
        const token = getComputedStyle(document.documentElement).getPropertyValue("--sticky-h");
        return parseFloat(token) * 16 - bottom;
      });

      expect(spare).toBeGreaterThanOrEqual(size.headroom);
    });

    test(`at ${size.name} (${size.width}px) opening the release switcher costs the stack nothing`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await page.goto(SECTION);

      const barHeight = () =>
        page.locator(".contextbar").evaluate((el) => el.getBoundingClientRect().height);

      const closed = await barHeight();
      await page.locator(".rpswitch__summary").click();
      await expect(page.locator(".rpswitch")).toHaveAttribute("open", "");
      await expect(page.locator("#asof")).toBeVisible();
      const open = await barHeight();

      // The panel is out of flow. In flow it is a label, a menu, a label, a
      // field, two buttons and a hint — about 180px of bar, which is the whole
      // reason ADR-0044 moved this control out of the chrome in the first place.
      expect(open).toBe(closed);
    });
  }
});

test.describe("the chapter rail stays put while the text scrolls", () => {
  /**
   * ADR-0050. `top` alone is what ADR-0043 tried and rejected — it pins the
   * rail and then lets it run past the bottom of the viewport, so the reader
   * cannot reach its tail without scrolling the document, which moves the text
   * they were trying to hold still. The bounded height is what makes the pin
   * worth having, so it is the thing asserted.
   */
  const SECTION = "/app/us/usc/t16/s45f";

  test("at 1280px the rail holds its place through a long scroll", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(SECTION);
    const rail = page.locator(".rail");
    await expect(rail).toBeVisible();

    const before = (await rail.boundingBox())!.y;
    await page.evaluate(() => window.scrollTo(0, 3000));
    await page.waitForTimeout(300);
    const after = (await rail.boundingBox())!.y;

    // Unpinned, 3000px of scroll takes the rail 3000px up and off the screen.
    expect(Math.abs(after - before)).toBeLessThan(40);
    expect(after).toBeGreaterThan(0);
  });

  test("the rail is bounded by the viewport and scrolls inside it", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(SECTION);

    const box = await page.evaluate(() => {
      const rail = document.querySelector(".rail") as HTMLElement;
      return {
        height: rail.getBoundingClientRect().height,
        overflowY: getComputedStyle(rail).overflowY,
        scrollHeight: rail.scrollHeight,
        clientHeight: rail.clientHeight,
      };
    });

    expect(box.overflowY).toBe("auto");
    expect(box.height).toBeLessThanOrEqual(900);
    // Title 16 subchapter I is longer than the space left under the chrome, so
    // this rail is one that has something to scroll. A rail that fitted would
    // make the assertion above vacuous.
    expect(box.scrollHeight).toBeGreaterThan(box.clientHeight);
  });

  test("below 64em the rail is not pinned", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(SECTION);
    const position = await page.evaluate(
      () => getComputedStyle(document.querySelector(".rail") as HTMLElement).position,
    );
    expect(position).toBe("static");
  });
});

test.describe("the guide's chapter list stays put while the chapter scrolls", () => {
  /**
   * The same arrangement as the rail above, and the same reason. It is a
   * separate block because the offset is a different number: `.rail` pins at
   * `--sticky-h`, the scroll-margin budget rounded up over the tallest chrome a
   * *section* page carries, and a guide page carries none of what makes that
   * stack tall — no context bar, no section bar.
   *
   * So the guide's rule writes 8rem, and this is what keeps that number honest.
   * The chrome above it is measured rather than assumed: it drifts every time
   * the navbar changes, which is the trap `--sticky-h`'s own comment has a
   * paragraph about.
   */
  const CHAPTER = "/app/guide/02-reading";

  test("at 1280px the chapter list holds its place through a long scroll", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(CHAPTER);
    const nav = page.locator(".guide__nav");
    await expect(nav).toBeVisible();

    const before = (await nav.boundingBox())!.y;
    await page.evaluate(() => window.scrollTo(0, 2500));
    await page.waitForTimeout(300);
    const after = (await nav.boundingBox())!.y;

    expect(Math.abs(after - before)).toBeLessThan(40);
    expect(after).toBeGreaterThan(0);
  });

  test("it pins under the chrome rather than behind it or below it", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(CHAPTER);
    await page.evaluate(() => window.scrollTo(0, 2500));
    await page.waitForTimeout(300);

    const measured = await page.evaluate(() => {
      let chrome = 0;
      for (const element of document.querySelectorAll("body *")) {
        const style = getComputedStyle(element);
        if (style.position !== "sticky" && style.position !== "fixed") continue;
        if (element.closest(".guide__nav")) continue;
        const box = element.getBoundingClientRect();
        if (box.height > 0 && box.top < 400 && box.bottom > chrome) chrome = box.bottom;
      }
      const nav = document.querySelector(".guide__nav") as HTMLElement;
      return { chrome, top: nav.getBoundingClientRect().top };
    });

    // Under it — the whole point of the pin — and not so far under it that the
    // list starts a third of the way down an empty column.
    expect(measured.top).toBeGreaterThanOrEqual(measured.chrome);
    expect(measured.top - measured.chrome).toBeLessThan(40);
  });

  test("it is bounded by the viewport and scrolls inside it", async ({ page }) => {
    // A short window, because the list is 355px of links and an assertion about
    // a list that fits is an assertion about nothing. 420px leaves 268 under
    // the chrome.
    await page.setViewportSize({ width: 1280, height: 420 });
    await page.goto(CHAPTER);

    const box = await page.evaluate(() => {
      const nav = document.querySelector(".guide__nav") as HTMLElement;
      return {
        height: nav.getBoundingClientRect().height,
        overflowY: getComputedStyle(nav).overflowY,
        scrollHeight: nav.scrollHeight,
        clientHeight: nav.clientHeight,
      };
    });

    expect(box.overflowY).toBe("auto");
    expect(box.height).toBeLessThanOrEqual(420);
    expect(box.scrollHeight).toBeGreaterThan(box.clientHeight);
  });

  test("below 64em it is not pinned", async ({ page }) => {
    // Stacked under the chapter on a phone, where a pinned contents list would
    // be ten links held over the prose they lead to.
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(CHAPTER);
    const position = await page.evaluate(
      () => getComputedStyle(document.querySelector(".guide__nav") as HTMLElement).position,
    );
    expect(position).toBe("static");
  });
});

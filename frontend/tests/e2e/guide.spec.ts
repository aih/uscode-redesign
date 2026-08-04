/**
 * The user guide, executed (ADR-0038).
 *
 * Every `scenario` block in `src/pages/guide/*.md` becomes one test here. The
 * guide says the site does something; this walks the steps it printed and
 * checks the thing it promised appears. A claim that stops being true fails the
 * build instead of sitting on a page misleading readers — which is exactly what
 * `/app/search/syntax` did for a fortnight, and the reason ADR-0038 exists.
 *
 * These are journey-level and stay that way. The deep assertions — a hover
 * card's three WCAG 1.4.13 clauses, a deep-linked provision clearing the sticky
 * bar, what each of four copy modes puts on the clipboard — live in the
 * hand-written specs beside this one and are not expressible in nine step
 * verbs. This file proves the documented path works; `preview.spec.ts` and
 * friends prove the feature is right.
 *
 * Scenarios are grouped by the context they need, because `test.use` is
 * per-describe: a scenario wanting a phone viewport, the clipboard, dark mode
 * or scripting off gets a describe block configured for it, and everything else
 * shares the default one.
 */
import { expect, test, type Page } from "@playwright/test";

// A plain-JS module, shared with `scripts/demovideo.mjs` — which is a bare node
// script and could not import a `.ts` one.
// @ts-expect-error - no type declarations for the shared .mjs extractor
import { readScenarios } from "../../scripts/scenarios.mjs";

interface Step {
  verb: string;
  value: any;
  caption: string | null;
}

interface Scenario {
  id: string;
  title: string;
  data: "fixture" | "corpus";
  needs: {
    viewport: "desktop" | "mobile";
    clipboard: boolean;
    colorScheme: string | null;
    javascript: boolean;
  };
  steps: Step[];
  chapterFile: string;
}

const scenarios: Scenario[] = readScenarios();

/** What a scenario's `needs` amount to, as one string, so scenarios wanting the
 * same context land in the same describe block. */
function profileKey(scenario: Scenario): string {
  const { viewport, clipboard, colorScheme, javascript } = scenario.needs;
  return JSON.stringify({ viewport, clipboard, colorScheme, javascript });
}

const profiles = new Map<string, Scenario[]>();
for (const scenario of scenarios) {
  const key = profileKey(scenario);
  if (!profiles.has(key)) profiles.set(key, []);
  profiles.get(key)!.push(scenario);
}

for (const [key, group] of profiles) {
  const needs = JSON.parse(key) as Scenario["needs"];

  const options: Record<string, unknown> = {};
  if (needs.viewport === "mobile") {
    options.viewport = { width: 375, height: 812 };
    options.hasTouch = true;
    options.isMobile = true;
  }
  if (needs.clipboard) options.permissions = ["clipboard-read", "clipboard-write"];
  if (needs.colorScheme) options.colorScheme = needs.colorScheme;
  if (!needs.javascript) options.javaScriptEnabled = false;

  test.describe(`guide (${describeProfile(needs)})`, () => {
    if (Object.keys(options).length > 0) test.use(options);

    for (const scenario of group) {
      test(`${scenario.id}: ${scenario.title}`, async ({ page }) => {
        // The full corpus is 58 titles; CI loads Title 16 at two release points
        // and nothing else (ADR-0013 — CI never fetches from OLRC). A scenario
        // needing more says so and is verified locally instead.
        test.skip(
          scenario.data === "corpus" && process.env.GUIDE_CORPUS !== "1",
          "needs the full corpus (run with GUIDE_CORPUS=1 against a fully loaded site)",
        );

        for (const [index, step] of scenario.steps.entries()) {
          await runStep(page, step, `${scenario.chapterFile} · ${scenario.id} · step ${index + 1}`);
        }
      });
    }
  });
}

function describeProfile(needs: Scenario["needs"]): string {
  const parts = [needs.viewport];
  if (needs.clipboard) parts.push("clipboard");
  if (needs.colorScheme) parts.push(needs.colorScheme);
  if (!needs.javascript) parts.push("no javascript");
  return parts.join(", ");
}

async function runStep(page: Page, step: Step, where: string): Promise<void> {
  switch (step.verb) {
    case "goto":
      await page.goto(step.value, { waitUntil: "load" });
      return;

    case "click":
      await page.locator(step.value).first().click();
      return;

    case "fill":
      await page.locator(step.value.selector).first().fill(step.value.value);
      return;

    // `fill` cannot drive a `<select>`; the release switcher is one, and
    // "switching release keeps the provision you were reading" is a claim the
    // guide has to be able to walk (ADR-0044).
    case "select":
      await page.locator(step.value.selector).first().selectOption(step.value.value);
      return;

    case "press":
      // Sent to the body rather than to a focused control: the keyboard
      // shortcuts this exercises are document-level listeners, and typing into
      // an input is the one case they deliberately ignore.
      await page.locator("body").press(step.value);
      return;

    case "hover":
      await page.locator(step.value).first().hover();
      return;

    case "focus":
      await page.locator(step.value).first().focus();
      return;

    case "scroll":
      await page.locator(step.value).first().scrollIntoViewIfNeeded();
      return;

    case "pause":
      // Capped hard. A pause in a scenario is pacing for the video, where a
      // step the eye cannot follow is a step nobody sees; here it is dead time,
      // and a guide author should not be able to make the suite slow by
      // writing a long one.
      await page.waitForTimeout(Math.min(step.value, 500));
      return;

    case "expect":
      await runExpect(page, step.value, where);
      return;

    default:
      throw new Error(`${where}: unknown step verb "${step.verb}"`);
  }
}

async function runExpect(page: Page, value: any, where: string): Promise<void> {
  if (value.url !== undefined) {
    // A substring, not a pattern: guide authors write URLs, and a URL is full
    // of characters a regular expression would read as syntax.
    await expect(page, where).toHaveURL(new RegExp(escapeRegExp(value.url)));
    return;
  }

  const locator = page.locator(value.selector).first();

  if (value.contains !== undefined) {
    await expect(locator, where).toContainText(value.contains);
    return;
  }

  if (value.count !== undefined) {
    await expect(page.locator(value.selector), where).toHaveCount(value.count);
    return;
  }

  if (value.visible !== undefined) {
    if (value.visible) await expect(locator, where).toBeVisible();
    else await expect(locator, where).toBeHidden();
    return;
  }

  throw new Error(`${where}: expect had nothing to assert`);
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

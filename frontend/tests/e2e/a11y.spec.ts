/**
 * The accessibility ratchet (ADR-0039).
 *
 * Every route in `docs/a11y/routes.json`, scanned by axe-core against
 * `wcag2a`, `wcag2aa`, `wcag21a` and `wcag21aa`, at three viewports, in both
 * themes (ADR-0027), and once with `forced-colors: active` — plus the
 * interactive states, because a violation that only exists while a preview is
 * open is not visible to a scanner that only ever loads pages.
 *
 * It is a ratchet rather than a pass/fail gate on a clean build. A violation
 * whose (route, rule) pair is listed in `docs/a11y/known-violations.json` is
 * allowed through; anything else fails. Serious and critical violations fail
 * even when listed, unless the entry carries an explicit `waived` block naming
 * an owner task and a date — so the default for a serious regression is a red
 * build, and every exception to that is a line somebody chose to write.
 *
 * Each scan writes a shard to `test-results/a11y/`; `a11y-report.ts` merges them
 * into `docs/verification/a11y.json` when the whole matrix has run. Sharding is
 * what makes the artifact correct under `fullyParallel` — the workers are
 * separate processes and cannot share an accumulator.
 *
 * Needs the site running: `make dev-all`, then `make test-a11y`.
 */
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { SHARD_DIR, type Finding, type Shard } from "./a11y-report";

const MATRIX = JSON.parse(
  readFileSync(fileURLToPath(new URL("../../../docs/a11y/routes.json", import.meta.url)), "utf8"),
);
const KNOWN = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../../../docs/a11y/known-violations.json", import.meta.url)),
    "utf8",
  ),
);

const GUIDE_DIR = fileURLToPath(new URL("../../src/pages/guide/", import.meta.url));

/** `usc-theme`, the one key ADR-0027's toggle writes. */
const THEME_KEY = "usc-theme";

interface Route {
  id: string;
  path: string;
  name: string;
  expectStatus?: number;
  /**
   * A selector the scan waits for before running axe, for a page whose content
   * is drawn by its own script rather than sent as markup.
   *
   * `load` on such a page fires on the shell, and axe then measures however much
   * of it had painted. On the two vendored bundles (ADR-0032) that is the whole
   * difference between a scan worth 169 nodes and one worth 1: unrendered, the
   * only rule that fires is `html-has-lang`, which reads the server's own
   * `<html>`. It is a race the settle timeout below usually wins and does not
   * always, which is what made the node count in `docs/verification/a11y.json`
   * differ between runs of identical code.
   */
  readyWhen?: string;
}

/**
 * The declared routes, with `expand: "guide-chapters"` resolved from disk.
 *
 * Reading the chapter list from the filesystem rather than naming nine paths
 * means a tenth chapter is scanned the day it lands, without anyone editing
 * this matrix — the same reason `guide.test.ts` walks `src/pages` instead of
 * asking the bundler.
 */
function routes(): Route[] {
  const out: Route[] = [];
  for (const entry of MATRIX.routes) {
    if (entry.expand === "guide-chapters") {
      for (const file of readdirSync(GUIDE_DIR).sort()) {
        if (!file.endsWith(".md")) continue;
        const slug = file.replace(/\.md$/, "");
        out.push({ id: `guide-${slug}`, path: `/app/guide/${slug}`, name: `guide: ${slug}` });
      }
      continue;
    }
    if (!entry.path) throw new Error(`route ${entry.id} has neither a path nor an expand rule`);
    out.push(entry as Route);
  }
  return out;
}

const ROUTES = routes();

/** Impacts that fail even when the pair is listed, absent an explicit waiver. */
const BLOCKING = new Set(["serious", "critical"]);

interface KnownEntry {
  rule: string;
  routes: string[];
  owner: string;
  reason: string;
  recorded: string;
  /**
   * The impact this entry is allowed to carry. A serious or critical violation
   * fails even when listed unless this names its exact impact, so a rule that
   * was moderate when it was recorded and has since become critical still turns
   * the build red.
   */
  waiveSeverity?: string;
}

function matched(routeId: string, rule: string): KnownEntry | undefined {
  return (KNOWN.entries as KnownEntry[]).find(
    (e) => e.rule === rule && (e.routes.includes("*") || e.routes.includes(routeId)),
  );
}

/**
 * The gate. Everything this spec asserts goes through here, so the rules about
 * what is and is not allowed live in exactly one place.
 */
function assertNoNewViolations(routeId: string, where: string, findings: Finding[]): void {
  const unexpected: string[] = [];

  for (const f of findings) {
    const entry = matched(routeId, f.id);
    if (!entry) {
      unexpected.push(
        `${f.id} (${f.impact}, ${f.nodes} nodes, first at \`${f.target}\`) — not in ` +
          `docs/a11y/known-violations.json. Fix it, or add an entry for route "${routeId}" ` +
          `with an owner task and a reason.`,
      );
      continue;
    }
    if (BLOCKING.has(f.impact ?? "") && entry.waiveSeverity !== f.impact) {
      unexpected.push(
        `${f.id} is ${f.impact} on "${routeId}" (${f.nodes} nodes, first at \`${f.target}\`). ` +
          `It is listed as known (owner ${entry.owner}), but its entry ` +
          `${entry.waiveSeverity ? `waives "${entry.waiveSeverity}", not "${f.impact}"` : `waives no severity`}. ` +
          `A ${f.impact} violation passes only when its entry sets ` +
          `"waiveSeverity": "${f.impact}".`,
      );
    }
  }

  expect(unexpected, `accessibility violations at ${where}`).toEqual([]);
}

/** Run axe, shard the result, and gate on it. */
async function scan(page: Page, routeId: string, where: string, key: string): Promise<void> {
  const result = await new AxeBuilder({ page }).withTags(MATRIX.axeTags).analyze();

  const findings: Finding[] = result.violations.map((v) => ({
    id: v.id,
    impact: v.impact ?? null,
    nodes: v.nodes.length,
    target: v.nodes[0]?.target?.join(" ") ?? "",
    help: v.help,
  }));

  const shard: Shard = { key, routeId, where, findings };
  mkdirSync(SHARD_DIR, { recursive: true });
  writeFileSync(join(SHARD_DIR, `${key}.json`), JSON.stringify(shard, null, 2));

  assertNoNewViolations(routeId, where, findings);
}

/** Load a route with the theme decided before the first paint. */
async function open(page: Page, route: Route, theme?: string): Promise<void> {
  if (theme) {
    await page.addInitScript(
      ([key, value]) => {
        try {
          localStorage.setItem(key, value);
        } catch {
          /* a browser refusing storage is not this test's subject */
        }
      },
      [THEME_KEY, theme] as const,
    );
  }
  const response = await page.goto(route.path, { waitUntil: "load" });
  const expected = route.expectStatus ?? 200;
  expect(response?.status(), `${route.path} answered unexpectedly`).toBe(expected);
  if (route.readyWhen) {
    // Not a settle timeout: a page that never draws is a scan of nothing, and
    // this suite would report it as a clean one.
    await page
      .locator(route.readyWhen)
      .first()
      .waitFor({ state: "attached", timeout: 20_000 });
  }
  // The islands settle after paint — the watch widget resolves to one button,
  // the copy column injects itself. Scanning before that measures a page no
  // reader ever sees. `make shots` waits for the same reason.
  await page.waitForTimeout(400);
}

function slug(...parts: (string | number)[]): string {
  return parts.join("--").replace(/[^a-zA-Z0-9-]+/g, "_");
}

for (const viewport of MATRIX.viewports as { width: number; height: number }[]) {
  for (const theme of MATRIX.themes as string[]) {
    test.describe(`axe ${viewport.width}px ${theme}`, () => {
      test.use({ viewport });

      for (const route of ROUTES) {
        test(`${route.id} — ${route.name}`, async ({ page }) => {
          await open(page, route, theme);
          await scan(
            page,
            route.id,
            `${route.path} at ${viewport.width}px in ${theme}`,
            slug(route.id, viewport.width, theme),
          );
        });
      }
    });
  }
}

test.describe("axe forced-colors", () => {
  test.use({ viewport: { width: 1280, height: 900 }, forcedColors: "active" });

  for (const route of ROUTES) {
    test(`${route.id} — ${route.name}`, async ({ page }) => {
      await open(page, route);
      await scan(page, route.id, `${route.path} with forced-colors: active`, slug(route.id, "fc"));
    });
  }
});

/**
 * The interactive states.
 *
 * Keyed by the ids declared in `routes.json`. The `states` test below asserts
 * that the two lists agree, so declaring a state and forgetting to implement it
 * is a failure rather than a silent gap in coverage.
 */
const SECTION = "/app/us/usc/t16/s45f";
const DIFF = "/app/diff/us/usc/t16/s45f?from=119-99&to=119-102not101";

const STATE_SETUP: Record<string, { routeId: string; setup: (page: Page) => Promise<void> }> = {
  "preview-focus": {
    routeId: "section",
    setup: async (page) => {
      await page.goto(SECTION, { waitUntil: "load" });
      await page.locator("a[data-cite]").first().focus();
      await expect(page.locator("#cite-preview")).toBeVisible({ timeout: 5000 });
    },
  },
  "preview-escape": {
    routeId: "section",
    setup: async (page) => {
      await page.goto(SECTION, { waitUntil: "load" });
      await page.locator("a[data-cite]").first().hover();
      await expect(page.locator("#cite-preview")).toBeVisible({ timeout: 5000 });
      await page.keyboard.press("Escape");
      await expect(page.locator("#cite-preview")).toBeHidden();
    },
  },
  "copy-active": {
    routeId: "section",
    setup: async (page) => {
      await page.goto(SECTION, { waitUntil: "load" });
      await page.locator(".copybtn").first().waitFor({ timeout: 5000 });
      await page.locator(".copybtn").nth(1).click();
      await expect(page.locator("[data-copy-status]")).not.toBeEmpty();
    },
  },
  "theme-toggled": {
    routeId: "section",
    setup: async (page) => {
      await page.goto(SECTION, { waitUntil: "load" });
      await page.locator(".navdrop--more > summary").click();
      // Scoped: there are two of these buttons (ADR-0064) and this scan runs at
      // the desktop viewport, where the menu's is the one displayed.
      await page.locator(".navdrop__list .theme-toggle").click();
      await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    },
  },
  "density-compact": {
    routeId: "section",
    setup: async (page) => {
      // The other reading setting (ADR-0054). It moves the reading size, the
      // leading and the paragraph gap, so it is a different rendering of the
      // same page rather than a different widget on it — the same reason
      // ADR-0027's themes are a whole axis of this matrix rather than a state.
      // It is one scan and not an axis because the tokens it moves are sizes,
      // and none of the rules here reads a size except through what it paints.
      await page.goto(SECTION, { waitUntil: "load" });
      await page.locator(".navdrop--more > summary").click();
      await page.locator("[data-density-toggle]").click();
      await expect(page.locator("html")).toHaveAttribute("data-density", "compact");
    },
  },
  "shortcuts-open": {
    routeId: "section",
    setup: async (page) => {
      // A modal `<dialog>` (ADR-0055). The page behind it is inert, so this
      // scan is of the dialog and its backdrop — the one state where axe sees
      // markup the closed page does not render at all.
      await page.goto(SECTION, { waitUntil: "load" });
      await page.keyboard.press("Shift+Slash");
      await expect(page.locator("#shortcuts")).toBeVisible({ timeout: 5000 });
    },
  },
  "palette-open": {
    routeId: "section",
    setup: async (page) => {
      // The second modal `<dialog>` on the site (ADR-0062), and the only state
      // in this matrix carrying a list of commands: eight rows, each a control
      // filling its own line, over a search form that is a second `role="search"`
      // on a page that already has one.
      await page.goto(SECTION, { waitUntil: "load" });
      await page.keyboard.press("ControlOrMeta+k");
      await expect(page.locator("#palette")).toBeVisible({ timeout: 5000 });
    },
  },
  "release-switcher-open": {
    routeId: "section",
    setup: async (page) => {
      // A `<details>` in the sticky bar (ADR-0056). Closed, the panel is not
      // rendered at all, so the two labelled controls and their buttons are
      // markup no other scan in this matrix reaches — and the panel is
      // absolutely positioned over the page, which is exactly the arrangement
      // that puts a control on top of another control's name.
      await page.goto(SECTION, { waitUntil: "load" });
      await page.locator(".rpswitch__summary").click();
      await page.locator("#asof").waitFor({ timeout: 5000 });
    },
  },
  "menus-open": {
    routeId: "section",
    setup: async (page) => {
      // Both site menus are `<details>` below 64em (ADR-0058), so this is the
      // one scan in the matrix that reaches them as menus at all — the rest of
      // it sees the navbar's list as a row and the footer's as a row. The
      // viewport is set here rather than by the describe block: at 1280 the
      // summary is `display: none` and there is nothing to open.
      //
      // It is also the only scan of the sheet in the shape B9 gave it
      // (ADR-0064) — More flattened into it, its group labels and both display
      // switches in the open — and of the 52px bar the sheet hangs from.
      await page.setViewportSize({ width: 375, height: 812 });
      await page.goto(SECTION, { waitUntil: "load" });
      await page.locator(".navmenu__summary").click();
      await expect(page.locator(".navmenu")).toHaveAttribute("open", "");
      await page.locator(".footmenu__summary").click();
      await expect(page.locator(".footmenu")).toHaveAttribute("open", "");
    },
  },
  "more-menu-open": {
    // Closed, this panel is not rendered at all, so its group labels, its two
    // display switches and the account row are markup no other scan in the
    // matrix reaches — and it is an absolutely positioned box over the page,
    // which is the arrangement that puts a control on top of another control's
    // name (ADR-0061).
    routeId: "section",
    setup: async (page) => {
      await page.goto(SECTION, { waitUntil: "load" });
      await page.locator(".navdrop--more > summary").click();
      await expect(page.locator(".navdrop--more")).toHaveAttribute("open", "", {
        timeout: 5000,
      });
    },
  },
  "titles-menu-open": {
    routeId: "section",
    setup: async (page) => {
      await page.goto(SECTION, { waitUntil: "load" });
      await page.locator(".navdrop--titles > summary").click();
      await expect(page.locator(".navdrop--titles")).toHaveAttribute("open", "", {
        timeout: 5000,
      });
    },
  },
  "diff-source-expanded": {
    routeId: "diff",
    setup: async (page) => {
      // The source redline is a round trip rather than a `<details>` — the cost
      // is in computing it, so `?source=1` is the state, not a disclosure
      // widget on an already-rendered page (ADR-0026).
      await page.goto(`${DIFF}&source=1#source`, { waitUntil: "load" });
      await page.locator(".diff-view--source").waitFor({ timeout: 15000 });
    },
  },
  "search-box-filled": {
    routeId: "section",
    setup: async (page) => {
      await page.goto(SECTION, { waitUntil: "load" });
      const box = page.locator("input[name='q']").first();
      await box.waitFor({ timeout: 5000 });
      await box.click();
      await box.fill("conservation");
    },
  },
};

test.describe("axe interactive states", () => {
  test.use({
    viewport: { width: 1280, height: 900 },
    permissions: ["clipboard-read", "clipboard-write"],
  });

  test("every state declared in routes.json has a setup here", () => {
    const declared = (MATRIX.states as { id: string }[]).map((s) => s.id).sort();
    expect(Object.keys(STATE_SETUP).sort(), "declared states and implemented states disagree").toEqual(
      declared,
    );
  });

  for (const state of MATRIX.states as { id: string; name: string }[]) {
    test(`${state.id} — ${state.name}`, async ({ page }) => {
      const implementation = STATE_SETUP[state.id];
      expect(implementation, `no setup for declared state "${state.id}"`).toBeTruthy();
      await implementation.setup(page);
      await page.waitForTimeout(200);
      await scan(page, implementation.routeId, `state: ${state.name}`, slug("state", state.id));
    });
  }
});

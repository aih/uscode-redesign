/**
 * The guide's scenario blocks: read, validated, and handed to whoever asked
 * (ADR-0038).
 *
 * A `scenario` fence inside a chapter of `src/pages/guide/` is three things at
 * once — the documented walkthrough a reader follows, a Playwright test in
 * `tests/e2e/guide.spec.ts`, and (when flagged `demo: true`) a captioned scene
 * of the video `scripts/demovideo.mjs` records. This module is the one place
 * that knows how to find them and what a valid one looks like, so those three
 * consumers cannot drift in their reading of the same block.
 *
 * It reads the filesystem rather than importing the chapters through Vite,
 * deliberately: the checker's job is to notice a chapter nobody wired up, and a
 * bundler-supplied file list cannot report a file the bundler never saw. It is
 * plain JS for the same class of reason — `demovideo.mjs` is a bare node
 * script, and a shared module the video generator cannot import is not shared.
 */

import { readFileSync, readdirSync } from "node:fs";
import { basename, join } from "node:path";
import { fileURLToPath } from "node:url";

import { parse } from "yaml";

export const GUIDE_DIR = fileURLToPath(new URL("../src/pages/guide/", import.meta.url));

/** The step verbs a scenario may use.
 *
 * Deliberately small (ADR-0038). These express "walk the documented path and
 * confirm what the guide says appears"; they are not meant to express the
 * assertions the hand-written specs carry — a hover card's dismissibility, a
 * deep link clearing the sticky bar — and any scenario straining against this
 * list is a sign the claim belongs in a spec instead. */
export const STEP_VERBS = [
  "goto",
  "click",
  "fill",
  "select",
  "press",
  "hover",
  "focus",
  "scroll",
  "expect",
  "pause",
];

const VIEWPORTS = ["desktop", "mobile"];
const DATA_SETS = ["fixture", "corpus"];

/** Every chapter file, in `order`, with its frontmatter and scenarios parsed. */
export function readChapters() {
  const files = readdirSync(GUIDE_DIR)
    .filter((name) => name.endsWith(".md"))
    .sort();

  const chapters = files.map((name) => {
    const path = join(GUIDE_DIR, name);
    const source = readFileSync(path, "utf8");
    const slug = basename(name, ".md");
    const frontmatter = parseFrontmatter(source, name);
    const scenarios = parseScenarios(source, slug, name);
    return { slug, file: name, path, frontmatter, scenarios };
  });

  chapters.sort((a, b) => (a.frontmatter.order ?? 0) - (b.frontmatter.order ?? 0));
  return chapters;
}

/** Every scenario in the guide, validated as a set (ids and demo order are
 * only checkable across chapters, not within one). */
export function readScenarios() {
  const chapters = readChapters();
  const scenarios = chapters.flatMap((chapter) => chapter.scenarios);

  const seen = new Map();
  for (const scenario of scenarios) {
    const clash = seen.get(scenario.id);
    if (clash) {
      throw new Error(
        `duplicate scenario id "${scenario.id}" in ${scenario.chapterFile} and ${clash}`,
      );
    }
    seen.set(scenario.id, scenario.chapterFile);
  }

  const orders = new Map();
  for (const scenario of scenarios.filter((s) => s.demo)) {
    const clash = orders.get(scenario.demoOrder);
    if (clash) {
      throw new Error(
        `two demo scenarios claim demoOrder ${scenario.demoOrder}: "${clash}" and "${scenario.id}"`,
      );
    }
    orders.set(scenario.demoOrder, scenario.id);
  }

  return scenarios;
}

/** The demo scenes, in the order the video plays them. */
export function demoScenes() {
  return readScenarios()
    .filter((scenario) => scenario.demo)
    .sort((a, b) => a.demoOrder - b.demoOrder);
}

function parseFrontmatter(source, file) {
  const match = /^---\r?\n([\s\S]*?)\r?\n---/.exec(source);
  if (!match) throw new Error(`${file}: no frontmatter`);

  const data = parse(match[1]) ?? {};
  if (!data.title) throw new Error(`${file}: frontmatter needs a title`);
  if (typeof data.order !== "number") {
    throw new Error(`${file}: frontmatter needs a numeric order`);
  }
  if (!data.layout) throw new Error(`${file}: frontmatter needs a layout`);

  const covers = data.covers ?? {};
  return {
    ...data,
    covers: { routes: covers.routes ?? [], adrs: covers.adrs ?? [] },
  };
}

function parseScenarios(source, slug, file) {
  const fence = /^```scenario\r?\n([\s\S]*?)^```/gm;
  const scenarios = [];
  let match;
  let position = 0;

  while ((match = fence.exec(source)) !== null) {
    position += 1;
    let raw;
    try {
      raw = parse(match[1]) ?? {};
    } catch (error) {
      throw new Error(`${file}: scenario ${position} is not valid YAML — ${error.message}`);
    }
    scenarios.push(validate(raw, { slug, file, position }));
  }

  return scenarios;
}

function validate(raw, { slug, file, position }) {
  const where = `${file}: scenario ${position}`;

  if (!raw.id) throw new Error(`${where} has no id`);
  if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(raw.id)) {
    throw new Error(`${where}: id "${raw.id}" must be kebab-case`);
  }
  if (!raw.title) throw new Error(`${where} ("${raw.id}") has no title`);
  if (!Array.isArray(raw.steps) || raw.steps.length === 0) {
    throw new Error(`${where} ("${raw.id}") has no steps`);
  }

  const data = raw.data ?? "fixture";
  if (!DATA_SETS.includes(data)) {
    throw new Error(`${where} ("${raw.id}"): data must be one of ${DATA_SETS.join(", ")}`);
  }

  const needs = raw.needs ?? {};
  const viewport = needs.viewport ?? "desktop";
  if (!VIEWPORTS.includes(viewport)) {
    throw new Error(
      `${where} ("${raw.id}"): needs.viewport must be one of ${VIEWPORTS.join(", ")}`,
    );
  }

  const steps = raw.steps.map((step, index) => validateStep(step, `${where} ("${raw.id}") step ${index + 1}`));

  const demo = raw.demo === true;
  if (demo && steps.some((step) => !step.caption)) {
    // A silent scene is worse than no scene: the video's only narration is
    // these captions, so a demo scenario has to say what each step is showing.
    throw new Error(`${where} ("${raw.id}") is a demo scene, so every step needs a caption`);
  }
  if (demo && typeof raw.demoOrder !== "number") {
    throw new Error(`${where} ("${raw.id}") is a demo scene, so it needs a numeric demoOrder`);
  }

  return {
    id: raw.id,
    title: raw.title,
    demo,
    demoOrder: raw.demoOrder ?? null,
    data,
    needs: {
      viewport,
      clipboard: needs.clipboard === true,
      colorScheme: needs.colorScheme ?? null,
      javascript: needs.javascript !== false,
    },
    steps,
    chapterSlug: slug,
    chapterFile: file,
  };
}

function validateStep(step, where) {
  if (typeof step !== "object" || step === null) {
    throw new Error(`${where} is not a mapping`);
  }

  const verbs = Object.keys(step).filter((key) => key !== "caption");
  if (verbs.length !== 1) {
    throw new Error(
      `${where} must name exactly one of ${STEP_VERBS.join(", ")} (found: ${verbs.join(", ") || "nothing"})`,
    );
  }

  const verb = verbs[0];
  if (!STEP_VERBS.includes(verb)) {
    throw new Error(`${where}: unknown step "${verb}" (known: ${STEP_VERBS.join(", ")})`);
  }

  const value = step[verb];

  if (verb === "fill" || verb === "select") {
    if (!value?.selector || typeof value.value !== "string") {
      throw new Error(`${where}: ${verb} needs { selector, value }`);
    }
  }

  if (verb === "expect") {
    const has =
      value?.contains !== undefined ||
      value?.visible !== undefined ||
      value?.inViewport !== undefined ||
      value?.count !== undefined ||
      value?.url !== undefined;
    if (!has) {
      throw new Error(`${where}: expect needs one of contains, visible, inViewport, count, url`);
    }
    if (value.url === undefined && !value.selector) {
      throw new Error(`${where}: expect needs a selector unless it is asserting url`);
    }
  }

  if (verb === "pause" && typeof value !== "number") {
    throw new Error(`${where}: pause takes a number of milliseconds`);
  }

  if (["goto", "click", "hover", "focus", "scroll", "press"].includes(verb)) {
    if (typeof value !== "string" || value.length === 0) {
      throw new Error(`${where}: ${verb} takes a non-empty string`);
    }
  }

  return { verb, value, caption: step.caption ?? null };
}

/** A step, said in English — the "How this is verified" box in the rendered
 * guide, and the log line the video generator prints. */
export function describeStep(step) {
  switch (step.verb) {
    case "goto":
      return `Open ${step.value}`;
    case "click":
      return `Click ${step.value}`;
    case "fill":
      return `Type “${step.value.value}” into ${step.value.selector}`;
    case "select":
      return `Choose “${step.value.value}” in ${step.value.selector}`;
    case "press":
      return `Press ${step.value}`;
    case "hover":
      return `Hover ${step.value}`;
    case "focus":
      return `Focus ${step.value}`;
    case "scroll":
      return `Scroll to ${step.value}`;
    case "pause":
      return `Wait ${step.value}ms`;
    case "expect": {
      const target = step.value.selector ? ` in ${step.value.selector}` : "";
      if (step.value.url !== undefined) return `Expect the URL to match ${step.value.url}`;
      if (step.value.contains !== undefined) {
        return `Expect “${step.value.contains}”${target}`;
      }
      if (step.value.count !== undefined) {
        return `Expect ${step.value.count} of ${step.value.selector}`;
      }
      // `inViewport` is the stronger claim: `visible` is true of an element
      // rendered a screen below the fold, which is no assertion at all about
      // something whose whole job was to scroll there.
      if (step.value.inViewport !== undefined) {
        return `Expect ${step.value.selector} to be ${step.value.inViewport === false ? "off" : "on"} screen`;
      }
      return `Expect ${step.value.selector} to be ${step.value.visible === false ? "hidden" : "visible"}`;
    }
    default:
      return step.verb;
  }
}

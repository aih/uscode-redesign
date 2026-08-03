/**
 * Renders a chapter's `scenario` fences as "How this is verified" boxes
 * (ADR-0038).
 *
 * Without this, Astro would print the raw YAML as a code block in the middle of
 * the prose — accurate, and useless to a reader who does not care that the
 * guide is executable. With it, the same block reads as what it is: the steps
 * someone would take, and the fact that a machine takes them on every push.
 *
 * The tree walk is written out rather than pulled from `unist-util-visit`
 * because it is nine lines and this file would otherwise be the only reason the
 * guide needs a dependency at all.
 *
 * Leniency is deliberate: a malformed block renders as best it can rather than
 * failing the build. The place a bad scenario is *supposed* to fail is
 * `tests/guide.test.ts`, with a message naming the chapter and the step —
 * failing here instead would mean a typo in a caption breaks `npm run build`
 * and tells you about it in a Vite stack trace.
 */
import { parse } from "yaml";

import { describeStep } from "./scenarios.mjs";

export function remarkScenario() {
  return (tree) => {
    walk(tree);
  };
}

function walk(node) {
  if (!node || !Array.isArray(node.children)) return;

  for (let i = 0; i < node.children.length; i += 1) {
    const child = node.children[i];
    if (child.type === "code" && child.lang === "scenario") {
      node.children[i] = { type: "html", value: render(child.value) };
    } else {
      walk(child);
    }
  }
}

function render(source) {
  let scenario;
  try {
    scenario = parse(source) ?? {};
  } catch {
    return `<pre class="scenario scenario--unparsed"><code>${escapeHtml(source)}</code></pre>`;
  }

  const steps = Array.isArray(scenario.steps) ? scenario.steps : [];
  const items = steps
    .map((step) => {
      const verbs = Object.keys(step ?? {}).filter((key) => key !== "caption");
      const verb = verbs[0];
      if (!verb) return "";
      const said = escapeHtml(describeStep({ verb, value: step[verb] }));
      const caption = step.caption
        ? `<span class="scenario__caption">${escapeHtml(step.caption)}</span>`
        : "";
      return `<li><span class="scenario__step">${said}</span>${caption}</li>`;
    })
    .join("");

  const badges = [
    scenario.demo === true ? '<span class="scenario__badge">in the demo video</span>' : "",
    scenario.data === "corpus"
      ? '<span class="scenario__badge scenario__badge--corpus">needs the full corpus</span>'
      : "",
  ].join("");

  return [
    '<details class="scenario">',
    '<summary class="scenario__summary">',
    `How this is verified: ${escapeHtml(scenario.title ?? scenario.id ?? "scenario")}`,
    "</summary>",
    '<div class="scenario__body">',
    `<p class="scenario__meta">These steps run as an automated test on every push, as <code>${escapeHtml(scenario.id ?? "")}</code>. ${badges}</p>`,
    `<ol class="scenario__steps">${items}</ol>`,
    "</div>",
    "</details>",
  ].join("");
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

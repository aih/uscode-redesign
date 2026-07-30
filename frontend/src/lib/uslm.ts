/**
 * USLM → HTML, element for element (ADR-0015 decision 2). This is the sole
 * place outside the parsers allowed to know a USLM element name (CLAUDE.md
 * architecture rule 5) — `api/` ships only the verbatim `SectionOut.xml`
 * fragment, and everything downstream of that happens here.
 *
 * Three things this port does that the Python renderer it replaces could not:
 * references resolve rather than being copied through verbatim (`refs.ts`),
 * hover text comes from labels the page already batched, and heading depth
 * tracks USLM nesting instead of emitting `<h2>` at every level (Day 7's
 * accessibility debt, cleared here).
 */

import { DOMParser } from "@xmldom/xmldom";

import type { Labels } from "./types";
import { resolveRef } from "./refs";

/** The handful of members this module actually calls on an xmldom node —
 * narrower than xmldom's own types, so a real `Element`/`Text` satisfies it
 * structurally without importing xmldom's types into every call site. */
export interface UslmNode {
  nodeType: number;
  nodeValue: string | null;
  childNodes: ArrayLike<UslmNode>;
}

export interface UslmElement extends UslmNode {
  tagName: string;
  localName: string | null;
  getAttribute(name: string): string | null;
}

const ELEMENT_NODE = 1;
const TEXT_NODE = 3;

export function parseFragment(xml: string): UslmElement {
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  return doc.documentElement as unknown as UslmElement;
}

/** Every `<ref href="…">` in the fragment, in document order, verbatim — the
 * raw material `refs.citedIdentifiers` and `resolveRef` work from. */
export function hrefs(fragment: UslmElement): string[] {
  const found: string[] = [];
  walk(fragment, (el) => {
    if (tagOf(el) === "ref") {
      const href = el.getAttribute("href");
      if (href) found.push(href);
    }
  });
  return found;
}

function walk(el: UslmElement, visit: (el: UslmElement) => void): void {
  visit(el);
  for (let i = 0; i < el.childNodes.length; i++) {
    const child = el.childNodes[i];
    if (child.nodeType === ELEMENT_NODE) walk(child as UslmElement, visit);
  }
}

function tagOf(el: UslmElement): string {
  return el.localName ?? el.tagName;
}

/** Containers that can carry their own `<heading>` — entering one is a step
 * down the outline, so a heading's `<hN>` tracks how many of these sit between
 * it and the section root instead of a flat `<h2>` everywhere (Day 7 debt). */
const LEVEL_TAGS = new Set([
  "title",
  "subtitle",
  "chapter",
  "subchapter",
  "part",
  "subpart",
  "division",
  "subdivision",
  "article",
  "subarticle",
  "section",
  "subsection",
  "paragraph",
  "subparagraph",
  "clause",
  "subclause",
  "item",
  "subitem",
  "level",
]);

/** Body text at a leaf: rendered as `<p>` so it gets ordinary paragraph
 * spacing without a `uslm-{tag}` div wrapper pretending to be a section. */
const PARAGRAPH_TAGS = new Set(["content", "continuation", "proviso", "chapeau"]);

/** Inline formatting — never a block, never renumbers the heading outline. */
const INLINE_TAGS: Record<string, string> = {
  i: "i",
  b: "b",
  sub: "sub",
  sup: "sup",
  span: "span",
  inline: "span",
  a: "span",
};

/** Real HTML table semantics, not `<div class="uslm-table">` soup. */
const TABLE_TAGS: Record<string, string> = {
  table: "table",
  thead: "thead",
  tbody: "tbody",
  tr: "tr",
  td: "td",
  th: "th",
  colgroup: "colgroup",
  col: "col",
};

/** Document-structure elements that never belong inside a rendered section
 * fragment; if one turns up (schema drift, a bad extraction) it is dropped
 * rather than dumped into the reading column. */
const SKIP_TAGS = new Set([
  "meta",
  "toc",
  "tocItem",
  "docNumber",
  "docPublicationName",
  "property",
]);

export interface RenderOptions {
  /** The identifier the URL actually named — highlighted with `.target`. */
  target: string | null;
  release: string | null;
  labels: Labels;
}

/** Renders the section root itself (not just its children): CSS depends on it
 * arriving as `.section-body > .uslm-section`, e.g. to hide the section's own
 * `<num>`/`<heading>` (already the page's `<h1>`). */
export function render(fragment: UslmElement, opts: RenderOptions): string {
  return renderElement(fragment, opts, 0);
}

function renderElement(el: UslmElement, opts: RenderOptions, depth: number): string {
  const tag = tagOf(el);
  if (tag.includes(":") || SKIP_TAGS.has(tag)) return "";

  const elDepth = LEVEL_TAGS.has(tag) ? depth + 1 : depth;

  if (tag === "heading") {
    const level = Math.min(Math.max(depth + 1, 2), 6);
    return wrapTag(`h${level}`, el, opts, elDepth, ["uslm-heading"]);
  }
  if (tag === "ref") return renderRef(el, opts);
  if (tag === "sourceCredit") return wrapDetails(el, opts, elDepth, "uslm-sourceCredit", "Source");
  if (tag === "notes") return wrapDetails(el, opts, elDepth, "uslm-notes", "Notes");
  if (tag === "br") return "<br/>";
  if (tag in TABLE_TAGS) return wrapTag(TABLE_TAGS[tag], el, opts, elDepth, [`uslm-${tag}`]);
  if (tag in INLINE_TAGS) return wrapTag(INLINE_TAGS[tag], el, opts, elDepth, [`uslm-${tag}`]);
  if (tag === "num") return wrapTag("span", el, opts, elDepth, ["uslm-num"]);
  if (PARAGRAPH_TAGS.has(tag)) return wrapTag("p", el, opts, elDepth, [`uslm-${tag}`]);

  // ADR-0015: a `<div>` fallback for every element this table does not name.
  return wrapTag("div", el, opts, elDepth, [`uslm-${tag}`]);
}

function renderChildren(el: UslmElement, opts: RenderOptions, depth: number): string {
  let out = "";
  for (let i = 0; i < el.childNodes.length; i++) {
    const node = el.childNodes[i];
    if (node.nodeType === ELEMENT_NODE) {
      out += renderElement(node as UslmElement, opts, depth);
    } else if (node.nodeType === TEXT_NODE) {
      out += escapeText(node.nodeValue ?? "");
    }
  }
  return out;
}

function wrapTag(
  htmlTag: string,
  el: UslmElement,
  opts: RenderOptions,
  childDepth: number,
  extraClasses: string[],
): string {
  const identifier = el.getAttribute("identifier");
  const classes = [...extraClasses];
  const sourceClass = el.getAttribute("class");
  if (sourceClass) classes.push(sourceClass);
  if (identifier && identifier === opts.target) classes.push("target");

  const attrs = [`class="${escapeAttr(classes.join(" "))}"`];
  if (identifier) attrs.push(`id="${escapeAttr(identifier)}"`);
  // ADR-0015: `@style` copied through verbatim. USLM's own values (e.g.
  // `-uslm-lc:I80`) are not real CSS declarations; a browser silently ignores
  // whatever it does not recognize, so this is inert rather than harmful.
  const style = el.getAttribute("style");
  if (style) attrs.push(`style="${escapeAttr(style)}"`);

  const inner = renderChildren(el, opts, childDepth);
  return `<${htmlTag} ${attrs.join(" ")}>${inner}</${htmlTag}>`;
}

function wrapDetails(
  el: UslmElement,
  opts: RenderOptions,
  depth: number,
  className: string,
  summary: string,
): string {
  // No JS (Day 4): `<details>` toggles natively. Rendered without the `open`
  // attribute — closed is the honest default everywhere — and `site.scss`
  // forces the content visible on desktop viewports only, per the spec
  // ("open by default on desktop, closed on mobile").
  const sourceClass = el.getAttribute("class");
  const classes = ["uslm-details", className, ...(sourceClass ? [sourceClass] : [])];
  const inner = renderChildren(el, opts, depth);
  return (
    `<details class="${escapeAttr(classes.join(" "))}">` +
    `<summary>${escapeText(summary)}</summary>${inner}</details>`
  );
}

function renderRef(el: UslmElement, opts: RenderOptions): string {
  const href = el.getAttribute("href") ?? "";
  const resolved = resolveRef(href, opts.release, opts.labels);
  const text = renderChildren(el, opts, 0);

  if (!resolved.href) {
    return `<span class="uslm-ref-plain">${text}</span>`;
  }
  const title = resolved.title ? ` title="${escapeAttr(resolved.title)}"` : "";
  const external = /^https?:\/\//u.test(resolved.href);
  const rel = external ? ' rel="noopener" class="usa-link usa-link--external"' : "";
  // `data-cite` is the hover-preview island's only hook, and it carries the
  // *identifier* rather than the href so the island never has to un-prefix
  // `/app` to build a preview URL. Internal references only: there is nothing
  // to preview at govinfo, and an unresolvable ref is not a link at all.
  //
  // `title` stays. It is what a reader with no JavaScript gets, what a screen
  // reader announces (the card is `aria-hidden` — see `CitePreview.astro`), and
  // what shows on a touch device, where the card never opens by design.
  // The release rides along so a preview is read at the same release point as
  // the page quoting it. Without it, a section being read at 119-99 would show
  // its cross references as they stand today — quietly mixing two vintages of
  // the law, which is the one thing this whole project exists to avoid.
  const cite = resolved.identifier
    ? ` data-cite="${escapeAttr(resolved.identifier)}"` +
      (opts.release ? ` data-cite-release="${escapeAttr(opts.release)}"` : "")
    : "";
  return `<a href="${escapeAttr(resolved.href)}"${title}${rel}${cite}>${text}</a>`;
}

/** Exported for the diff view (Day 4): a redline of raw XML source has to
 * escape the same way a rendered text node does. */
export function escapeHtml(value: string): string {
  return value.replace(/&/gu, "&amp;").replace(/</gu, "&lt;").replace(/>/gu, "&gt;");
}

function escapeText(value: string): string {
  return escapeHtml(value);
}

function escapeAttr(value: string): string {
  return escapeText(value).replace(/"/gu, "&quot;");
}

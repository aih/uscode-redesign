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

/**
 * Every provision in the fragment that is worth offering a copy control for, in
 * document order, the section itself first.
 *
 * "Worth offering" is two conditions, and both matter:
 *
 *   * It carries an `@identifier`, so there is something to cite and a URL that
 *     addresses it. Anything without one has no citation to copy.
 *   * It is a `LEVEL_TAGS` container — a subsection, paragraph, clause and so
 *     on. Not every identified element is a provision: `<num>`, `<heading>` and
 *     `<content>` can carry identifiers too, and a copy button on the number of
 *     a paragraph, immediately next to the one on the paragraph, is two
 *     controls that do almost the same thing an inch apart.
 *
 * This function is in `uslm.ts` rather than next to the widget because it is
 * the one module allowed to know USLM element names (CLAUDE.md architecture
 * rule 5) — `LEVEL_TAGS` is already the list, already maintained for the
 * heading outline, and a second copy of it in a component is exactly the kind
 * of duplication that rule exists to prevent.
 */
export function copyableIdentifiers(fragment: UslmElement): string[] {
  const found: string[] = [];
  const seen = new Set<string>();
  walk(fragment, (el) => {
    if (!LEVEL_TAGS.has(tagOf(el))) return;
    const identifier = el.getAttribute("identifier");
    // The source publishes the odd repeated identifier at one release point
    // (ADR-0021); the page renders every occurrence, so `getElementById` would
    // find only the first. One control, on the first, rather than a second that
    // silently copies the wrong body.
    if (!identifier || seen.has(identifier)) return;
    seen.add(identifier);
    found.push(identifier);
  });
  return found;
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
  // A cross reference opens in a new tab, so that following one does not cost
  // the reader the provision they were reading — the case this is for is
  // "what does § 1531 say", asked in the middle of a sentence, and the answer
  // is useless if getting it means losing the sentence.
  //
  // Baked into the HTML rather than applied by script, because these pages are
  // served from a shared cache (ADR-0018) and cannot vary per reader. That
  // makes new-tab the behaviour with scripting off, which is the right default
  // to fail to; `data-newtab` is the handle the reader's preference uses to
  // take it back off again (`Base.astro`).
  //
  // `rel="noopener"` is not optional next to `target="_blank"`: without it the
  // opened page gets a live `window.opener` handle on this one. It is written
  // once here rather than appended to the external case's `rel`, because two
  // `rel` attributes on one tag is invalid HTML and the second is discarded —
  // which would have silently dropped exactly the protection govinfo links
  // need most.
  const rel = external
    ? ' target="_blank" rel="noopener" data-newtab class="usa-link usa-link--external"'
    : ' target="_blank" rel="noopener" data-newtab';
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

/* ----------------------------------------------------------- reading text
 *
 * The same document, as lines of text rather than HTML — what the diff view
 * needs (ADR-0026). A redline of raw XML shows a reader `<ref href="…">` churn
 * and regenerated `@id`s; a redline of *this* shows what the law now says.
 *
 * It lives here because deciding where one line of statutory text ends is a
 * USLM question — `<num>` and its `<chapeau>` are one line to a reader, a
 * `<paragraph>` under them is another — and this module is the only place
 * outside the parsers allowed to ask one (architecture rule 5).
 */

/** Elements that end the line being accumulated. Every level, plus the
 * apparatus that is visibly its own block but is not a level: notes, source
 * credit, quoted statutory text, table rows. Everything else — `<num>`,
 * `<heading>`, `<content>`, `<chapeau>`, `<ref>`, `<i>` — flows into the
 * current line, which is what makes "(a) In general.—The Secretary shall…"
 * come out as one line instead of four. */
const LINE_BREAK_TAGS = new Set([
  ...LEVEL_TAGS,
  // `<p>` is how a note's own paragraphs are marked up, and a note can be an
  // entire Executive Order. Without this, one of them is a single "line" and a
  // three-word amendment inside it redlines as a wall of text.
  "p",
  "notes",
  "note",
  "sourceCredit",
  "quotedContent",
  "quotedText",
  "table",
  "tr",
  "toc",
]);

const NOTE_TAGS = new Set(["notes", "note", "sourceCredit"]);

export type ReadingKind = "text" | "note";

export interface ReadingBlock {
  /** Outline depth, counted in levels — the diff view spends it as indentation
   * so a changed clause still reads at the depth it lives at. */
  depth: number;
  /** Statutory text, or the apparatus around it. The two are worth telling
   * apart in a redline: a changed note is not a changed law. */
  kind: ReadingKind;
  /** Whitespace-normalized. Two release points differ in indentation of the
   * source constantly and in meaning rarely; normalizing here is what keeps
   * reformatting out of the redline. */
  text: string;
}

/** The fragment as the lines a reader reads, in document order. */
export function readingBlocks(fragment: UslmElement): ReadingBlock[] {
  const blocks: ReadingBlock[] = [];
  collectBlocks(fragment, 1, "text", blocks);
  return blocks;
}

function collectBlocks(
  el: UslmElement,
  depth: number,
  kind: ReadingKind,
  out: ReadingBlock[],
): void {
  let line = "";

  const flush = (): void => {
    const text = normalizeSpace(line);
    line = "";
    if (text) out.push({ depth, kind, text });
  };

  for (let i = 0; i < el.childNodes.length; i++) {
    const node = el.childNodes[i];
    if (node.nodeType === TEXT_NODE) {
      line += node.nodeValue ?? "";
      continue;
    }
    if (node.nodeType !== ELEMENT_NODE) continue;

    const child = node as UslmElement;
    const tag = tagOf(child);
    if (tag.includes(":") || SKIP_TAGS.has(tag)) continue;

    if (LINE_BREAK_TAGS.has(tag)) {
      // Flush *before* descending, and keep accumulating after: a
      // `<continuation>` that follows a nested paragraph belongs after that
      // paragraph, not merged into the line that introduced it.
      flush();
      collectBlocks(
        child,
        LEVEL_TAGS.has(tag) ? depth + 1 : depth,
        NOTE_TAGS.has(tag) ? "note" : kind,
        out,
      );
    } else if (tag in INLINE_TAGS || tag === "ref") {
      // Inline formatting is part of the word it sits in — `10<sup>3</sup>` is
      // one token, not two.
      line += inlineText(child);
    } else {
      // A `<num>`, a `<heading>`, a `<content>`: separate blocks in the render,
      // one line here, and the source is free to put no whitespace between
      // them — so `(a)` and its chapeau must not run together as `(a)Whoever`.
      line = join(line, inlineText(child));
    }
  }

  flush();
}

function join(left: string, right: string): string {
  if (!left || !right) return left + right;
  return /\s$/u.test(left) || /^\s/u.test(right) ? left + right : `${left} ${right}`;
}

function inlineText(el: UslmElement): string {
  let out = "";
  for (let i = 0; i < el.childNodes.length; i++) {
    const node = el.childNodes[i];
    if (node.nodeType === TEXT_NODE) {
      out += node.nodeValue ?? "";
    } else if (node.nodeType === ELEMENT_NODE) {
      const child = node as UslmElement;
      const tag = tagOf(child);
      if (tag.includes(":") || SKIP_TAGS.has(tag)) continue;
      out += inlineText(child);
    }
  }
  return out;
}

function normalizeSpace(value: string): string {
  return value.replace(/\s+/gu, " ").trim();
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

/**
 * A search highlight fragment, made safe to put in `set:html`.
 *
 * OpenSearch's highlighter wraps matched terms in `<em>` and **does not escape
 * the field content around them** — it returns the stored text as it was
 * indexed. So the fragment is not trusted markup, it is untrusted text with two
 * known tags in it, and the safe reading is exactly that: escape everything,
 * then put back the one pair of tags the highlighter is documented to add.
 *
 * Not currently exploitable, and that is a property of the indexer rather than
 * of this page: `ingest/search_sync.strip_xml_tags` removes markup before
 * indexing and never decodes entities, so no raw `<` reaches the index today.
 * One change to that function and it would — which is the whole reason this
 * escapes at the boundary rather than trusting the pipeline to stay as it is.
 */
export function highlightHtml(fragment: string): string {
  return escapeHtml(fragment)
    .replace(/&lt;em&gt;/gu, "<em>")
    .replace(/&lt;\/em&gt;/gu, "</em>");
}

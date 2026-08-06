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
import { citationHref } from "./url";

/** The handful of members this module actually calls on an xmldom node —
 * narrower than xmldom's own types, so a real `Element`/`Text` satisfies it
 * structurally without importing xmldom's types into every call site. */
export interface UslmNode {
  nodeType: number;
  nodeValue: string | null;
  childNodes: ArrayLike<UslmNode>;
  /** Needed by `inRunningProse`: whether an element sits in a sentence is a
   * fact about its siblings, not about the element. */
  previousSibling?: UslmNode | null;
  nextSibling?: UslmNode | null;
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

/** The `id` the section's own source credit and notes are rendered with when
 * `RenderOptions.anchors` is set, and the only fragment names the reader's
 * in-section navigation targets that USLM does not already supply.
 *
 * Every provision has an `@identifier` and is rendered with it as its `id`, so
 * `(a)` is reachable as `#/us/usc/t16/s45f/a` with nothing invented. The
 * apparatus has no identifier of its own — a `<notes>` container carries no
 * attribute distinguishing it from any other — so these two are named here. */
export const SOURCE_ANCHOR = "section-source";
export const NOTES_ANCHOR = "section-notes";

/** One row of a section's own contents: a top-level provision, or the source
 * credit or notes block underneath them. */
export interface OutlineEntry {
  /** The fragment name to link to, without the `#`. */
  anchor: string;
  /** `(a)`, or the apparatus block's name. */
  num: string;
  /** The provision's heading where the source writes one. */
  heading: string | null;
}

/**
 * A section's own table of contents: its top-level provisions, then its source
 * credit and notes.
 *
 * Top level only, and deliberately. The ladder goes seven deep
 * (`docs/verification/ladder.json`), and a contents list that recursed would be
 * longer than the section it indexes for anything below `(a)(1)`. What a reader
 * wants from it is the shape of the section and a way into the apparatus, both
 * of which the first rung answers.
 *
 * Here rather than in the component that renders it, for the same reason
 * `copyableIdentifiers` is: `LEVEL_TAGS` is the list of what counts as a
 * provision, and architecture rule 5 keeps USLM element names in this module.
 */
export function outline(fragment: UslmElement): OutlineEntry[] {
  const entries: OutlineEntry[] = [];
  const seen = new Set<string>();
  let source = false;
  let notes = false;

  for (let i = 0; i < fragment.childNodes.length; i++) {
    const node = fragment.childNodes[i];
    if (node.nodeType !== ELEMENT_NODE) continue;
    const child = node as UslmElement;
    const tag = tagOf(child);

    if (tag === "sourceCredit") {
      source = true;
      continue;
    }
    if (tag === "notes") {
      notes = true;
      continue;
    }
    if (!LEVEL_TAGS.has(tag)) continue;

    const identifier = child.getAttribute("identifier");
    // Same rule as `copyableIdentifiers`: the source repeats the odd identifier
    // at one release point (ADR-0021) and a fragment name addresses the first
    // element carrying it, so a second row would link to the first one's text.
    if (!identifier || seen.has(identifier)) continue;
    seen.add(identifier);

    const num = normalizeSpace(childText(child, "num"));
    // A provision with no `<num>` has nothing to label a contents row with —
    // "" would render as an empty link, which is a WCAG 2.4.4 failure and no
    // use to anyone. There is no fallback worth inventing: the row is dropped
    // and the provision is still reachable by scrolling.
    if (!num) continue;
    entries.push({
      anchor: identifier,
      num,
      heading: normalizeSpace(childText(child, "heading")) || null,
    });
  }

  if (source) entries.push({ anchor: SOURCE_ANCHOR, num: "Source credit", heading: null });
  if (notes) entries.push({ anchor: NOTES_ANCHOR, num: "Notes", heading: null });
  return entries;
}

/** The text of the first direct child with this tag — `<num>` or `<heading>`,
 * which is all `outline` asks for. Direct children only: a nested provision's
 * number is not this one's. */
function childText(el: UslmElement, tag: string): string {
  for (let i = 0; i < el.childNodes.length; i++) {
    const node = el.childNodes[i];
    if (node.nodeType !== ELEMENT_NODE) continue;
    const child = node as UslmElement;
    if (tagOf(child) === tag) return inlineText(child);
  }
  return "";
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

/**
 * Inline formatting — never a block, never renumbers the heading outline.
 *
 * Every element here was measured to occur in running prose rather than
 * guessed at from the schema: `scripts/inline_elements.py` counts, across the
 * committed samples, how often each element sits beside a non-whitespace text
 * node. `docs/verification/inline-elements.json` is the result, and
 * `tests/uslm.test.ts` walks it element by element.
 *
 * `date` and `footnote` occur that way **20,513 and 1,051 times and never
 * otherwise** — zero isolated occurrences between them. Both used to fall
 * through to the `<div>` at the bottom of `renderElement`, which put a block in
 * the middle of a sentence throughout the editorial notes. That is WCAG 1.3.2:
 * a block reorders the sequence a screen reader announces, mid-sentence, in the
 * one part of the page a drafter reads for amendment history.
 */
const INLINE_TAGS: Record<string, string> = {
  i: "i",
  b: "b",
  sub: "sub",
  sup: "sup",
  span: "span",
  inline: "span",
  a: "span",
  date: "span",
  footnote: "span",
};

/**
 * Elements the source uses both ways, decided per occurrence.
 *
 * `<note>` is an editorial note 30,981 times and an inline footnote marker 883
 * times ("…the Act of March 1, 1872, *1 See References in Text note below.*
 * reserving lands for park purposes…"). `<quotedContent>` is a block quotation
 * 875 times and a quoted phrase inside a sentence 2,701 times. Neither can be
 * classified by name, so `inRunningProse` asks the markup: an element with a
 * non-whitespace text node immediately beside it is in a sentence, whatever it
 * is called.
 *
 * `<p>` (50 of 58,865), `<table>` (26 of 822), `<list>` (8 of 36), `<heading>`
 * (3 of 87,190) and `<proviso>` (2 of 5) also appear beside text, and are
 * deliberately not here: at well under 1% those are the source being odd, and a
 * heading rendered as a span would cost the outline that A4 depends on more
 * than three sentences are worth.
 */
const CONTEXTUAL_TAGS = new Set(["note", "quotedContent"]);

/** Statutory text quoted by an amending act, rendered as a block quotation.
 * `quotedContent` reaches this only when `inRunningProse` says it is not part
 * of a sentence; `quotedText` occurs in neither schema's samples and is here
 * because the schema defines it and the two mean the same thing to a reader. */
const QUOTE_TAGS = new Set(["quotedContent", "quotedText"]);

/** A non-whitespace text node immediately before or after — the same test
 * `scripts/inline_elements.py` counts with. */
function inRunningProse(el: UslmElement): boolean {
  const filled = (node: UslmNode | null | undefined): boolean =>
    node?.nodeType === TEXT_NODE && (node.nodeValue ?? "").trim() !== "";
  return filled(el.previousSibling) || filled(el.nextSibling);
}

/** Real HTML table semantics, not `<div class="uslm-table">` soup.
 *
 * USLM 2.x writes these in the XHTML namespace — `xhtml:table`, `xhtml:td`,
 * 781 tables in `usc49.xml` alone — which arrive here as their local names and
 * so need no separate vocabulary. `caption` is one of them (766 occurrences)
 * and used to fall through to the `<div>` at the bottom of `renderElement`: a
 * `<div>` is not valid inside a `<table>`, so the browser hoisted it out and
 * the table lost its own title. It is also the only accessible name a table
 * carries, which is what `renderTable` labels the scroll region with. */
const TABLE_TAGS: Record<string, string> = {
  table: "table",
  caption: "caption",
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
  /**
   * Name the section's own source credit and notes blocks, so the in-section
   * navigation has somewhere to point.
   *
   * Off by default, and a caller opts in exactly once per document. A fragment
   * name has to be unique in the page it lands in, and three things render this
   * markup into one page: the section, any further occurrence the source
   * publishes under the same identifier (ADR-0021), and the hover card, which
   * inserts a *different* section's body into the document the reader is on. If
   * this were unconditional, all three would carry `id="section-notes"` and the
   * link would go to whichever the browser met first.
   */
  anchors?: boolean;
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
  if (CONTEXTUAL_TAGS.has(tag) && inRunningProse(el)) {
    return wrapTag("span", el, opts, elDepth, [`uslm-${tag}`, "uslm-inlined"]);
  }
  // Statutory text quoted by an amending act, as its own block. `<blockquote>`
  // rather than a `<div>`, so that the boundary between the law in force and
  // the words an amendment is moving around is carried by the markup and not
  // only by the rule down its left edge (ADR-0054). A `<section>` inside one is
  // not a section (ADR-0005) — it renders here, with its own number and
  // heading, inside the quotation that owns it.
  if (QUOTE_TAGS.has(tag)) return wrapTag("blockquote", el, opts, elDepth, [`uslm-${tag}`]);
  // `depth === 1` is a direct child of the section root — the section's own
  // apparatus, as against a note hanging off a subsection deeper down. Only
  // that one is named, and only when the caller asked (`RenderOptions.anchors`).
  if (tag === "sourceCredit") {
    const id = opts.anchors && depth === 1 ? SOURCE_ANCHOR : null;
    return wrapDetails(el, opts, elDepth, "uslm-sourceCredit", "Source", id);
  }
  if (tag === "notes") {
    const id = opts.anchors && depth === 1 ? NOTES_ANCHOR : null;
    return wrapDetails(el, opts, elDepth, "uslm-notes", "Notes", id);
  }
  if (tag === "br") return "<br/>";
  if (tag === "table") return renderTable(el, opts, elDepth);
  if (tag in TABLE_TAGS) return wrapTag(TABLE_TAGS[tag], el, opts, elDepth, [`uslm-${tag}`]);
  if (tag in INLINE_TAGS) return wrapTag(INLINE_TAGS[tag], el, opts, elDepth, [`uslm-${tag}`]);
  if (tag === "num") return wrapTag("span", el, opts, elDepth, ["uslm-num"]);
  if (PARAGRAPH_TAGS.has(tag)) return wrapTag("p", el, opts, elDepth, [`uslm-${tag}`]);

  // ADR-0015: a `<div>` fallback for every element this table does not name.
  // A level below the section root also carries `prov`, which is the whole of
  // what the stylesheet needs to know to build the (a)/(1)/(A)/(i) ladder: one
  // step of indent per nesting, numbers hanging into it. The class is emitted
  // here rather than the stylesheet enumerating `uslm-subsection`,
  // `uslm-paragraph` and the rest, because `LEVEL_TAGS` is already that list
  // and architecture rule 5 keeps USLM element names in this module.
  //
  // `depth > 0` excludes the fragment's own root: the section is the column,
  // not a rung in it.
  const ladder = LEVEL_TAGS.has(tag) && depth > 0 ? ["prov"] : [];
  return wrapTag("div", el, opts, elDepth, [`uslm-${tag}`, ...ladder]);
}

/**
 * A table, inside a region a keyboard can reach.
 *
 * Wide tables scroll sideways inside themselves rather than pushing the page
 * sideways (`site.scss`). A scrollable box that nothing can focus is
 * unreachable without a pointer — axe's `scrollable-region-focusable`, and one
 * of the two instances already on `docs/a11y/known-violations.json`. The
 * wrapper is the fix and it ships with the table rather than after it.
 *
 * The region is named from the table's own `<caption>` where there is one; the
 * bare "Table" is the fallback for USLM 1.x, which writes none.
 */
function renderTable(el: UslmElement, opts: RenderOptions, depth: number): string {
  const table = wrapTag("table", el, opts, depth, ["uslm-table"]);
  const label = captionText(el) || "Table";
  return (
    `<div class="uslm-tablewrap" role="region" tabindex="0" ` +
    `aria-label="${escapeAttr(label)}">${table}</div>`
  );
}

function captionText(table: UslmElement): string {
  for (let i = 0; i < table.childNodes.length; i++) {
    const node = table.childNodes[i];
    if (node.nodeType !== ELEMENT_NODE) continue;
    const child = node as UslmElement;
    if (tagOf(child) === "caption") return normalizeSpace(inlineText(child));
  }
  return "";
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
  id: string | null = null,
): string {
  // No JS (Day 4): `<details>` toggles natively. Rendered without the `open`
  // attribute — closed is the honest default everywhere — and `site.scss`
  // forces the content visible on desktop viewports only, per the spec
  // ("open by default on desktop, closed on mobile").
  const sourceClass = el.getAttribute("class");
  const classes = ["uslm-details", className, ...(sourceClass ? [sourceClass] : [])];
  const inner = renderChildren(el, opts, depth);
  const idAttr = id ? ` id="${escapeAttr(id)}"` : "";
  return (
    `<details class="${escapeAttr(classes.join(" "))}"${idAttr}>` +
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
  // What the print stylesheet prints after the link text (ADR-0054). A
  // reference is the one thing on a printed page that stops working, and
  // `attr(href)` would print `/app/us/usc/…` — the reader's own prefix, which
  // is not the form worth writing down. `citationHref` is (`url.ts`): the bare
  // citation URL, carrying the release point so the printed reference resolves
  // to the same vintage as the page it was printed from. An external reference
  // already has a whole URL in its href and keeps it.
  const printUrl = resolved.identifier
    ? citationHref(resolved.identifier, opts.release)
    : resolved.href;
  return (
    `<a href="${escapeAttr(resolved.href)}"${title}${rel}${cite}` +
    ` data-print-url="${escapeAttr(printUrl)}">${text}</a>`
  );
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

    if (CONTEXTUAL_TAGS.has(tag) && inRunningProse(child)) {
      // The same judgement the renderer makes, for the same reason: a `<note>`
      // that is a footnote marker inside a sentence is part of that sentence.
      // Left to `LINE_BREAK_TAGS` below it would flush, and one sentence would
      // redline as three blocks.
      line += inlineText(child);
    } else if (LINE_BREAK_TAGS.has(tag)) {
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

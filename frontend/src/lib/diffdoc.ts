/**
 * A redline of what a section *says*, not of the XML it is stored as
 * (ADR-0026, amending ADR-0016).
 *
 * The API's `/sections/{id}/diff` is a source-level diff of two verbatim XML
 * fragments, and that is the right thing for an API to serve — but it is the
 * wrong thing to put in front of a reader. Guids regenerate at every release
 * point by design (CLAUDE.md gotcha 1), so the raw redline of an untouched
 * section is hundreds of changed `@id` attributes and no changed words; the
 * load test measured about half the diff's cost as exactly that churn. What a
 * reader wants is the sentence that changed.
 *
 * So this module diffs `readingBlocks()` — the document as lines of text — in
 * two passes, which is what makes the output a document rather than a stream:
 *
 *   1. **Align the lines.** Each distinct line becomes one character, and
 *      diff-match-patch aligns the two character strings. This is the standard
 *      line-mode trick, and it is why a paragraph inserted in the middle does
 *      not shift everything after it into "changed".
 *   2. **Diff inside a line that survived.** A deleted line paired with an
 *      inserted line is usually one line *edited*, so it is diffed word by word
 *      and shown as one line — but only if the two are actually related.
 *      Unrelated pairs stay a deletion and an insertion, because pretending
 *      that one sentence "became" an unrelated one is worse than showing both.
 *
 * `Diff_Timeout = 0` throughout, ported for the same reason `api/diff.py` does
 * it: diff-match-patch silently returns a *worse* diff once it times out
 * (docs/prior-art.md), and a redline that is subtly wrong is the one failure
 * mode this view cannot have.
 */

import DiffMatchPatch from "diff-match-patch";

import type { ReadingBlock, ReadingKind } from "./uslm";
import { escapeHtml } from "./uslm";

export type Mark = "equal" | "insert" | "delete";

/** A run of characters within a line, and what happened to it. */
export interface Span {
  mark: Mark;
  text: string;
}

export interface DiffLine {
  /** `changed` is a line that exists on both sides with edits inside it. */
  mark: Mark | "changed";
  depth: number;
  kind: ReadingKind;
  spans: Span[];
}

export interface DocumentDiff {
  lines: DiffLine[];
  /** Line counts, for telling a reader up front whether this is a typo fix or
   * a rewrite — and, when all three are zero, that nothing changed at all. */
  changed: number;
  inserted: number;
  deleted: number;
}

/**
 * What separates two source fragments whose *reading text* came out identical.
 *
 * "Nothing changed" and "nothing you can read changed" are different claims,
 * and this view can only ever establish the second one. Reporting the first is
 * how a reader concludes the source republished nothing, when in fact it
 * republishes this section at every release point (gotcha 1) — so when the
 * redline is empty, the page says which of these three it actually found.
 *
 *   - `identical` — the two fragments are byte-for-byte the same. Under
 *     ADR-0007's dedupe this is the ordinary case: both release points resolve
 *     to one stored `section_versions` row, guids included.
 *   - `guids-only` — they differ, and stripping `@id` makes them equal. This is
 *     the churn ADR-0026 moved the reader off: regenerated per release point by
 *     design, and legally nothing.
 *   - `beyond-guids` — they differ by something else. Whitespace, `@temporalId`,
 *     an attribute, a structural change that carries no words. Worth saying,
 *     because ADR-0026's named cost is that a whitespace-only change is exactly
 *     what this reading view cannot see.
 */
export type SourceDelta = "identical" | "guids-only" | "beyond-guids";

/** `@id` and nothing else: `\s` before it keeps this off `temporalId=` and
 *  `xml:id=`, whose preceding characters are a letter and a colon. */
const GUID_ATTR = /\sid=("[^"]*"|'[^']*')/gu;

export function sourceDelta(before: string, after: string): SourceDelta {
  if (before === after) return "identical";
  if (before.replace(GUID_ATTR, "") === after.replace(GUID_ATTR, "")) {
    return "guids-only";
  }
  return "beyond-guids";
}

const EQUAL = 0;
const INSERT = 1;
const DELETE = -1;

/** How much two lines must have in common before they are shown as one edited
 * line rather than as a deletion and an unrelated insertion. Measured as the
 * share of the longer line that survives the edit. 0.4 keeps "struck out
 * '$5,000,000' and inserted '$7,500,000'" together — the case this view exists
 * for — while a wholly rewritten subsection still shows as both texts. */
const PAIR_THRESHOLD = 0.4;

function engine(): DiffMatchPatch {
  const dmp = new DiffMatchPatch();
  dmp.Diff_Timeout = 0; // never trade correctness for speed (docs/prior-art.md)
  return dmp;
}

export function documentDiff(from: ReadingBlock[], to: ReadingBlock[]): DocumentDiff {
  const ops = alignLines(from, to);

  const lines: DiffLine[] = [];
  let changed = 0;
  let inserted = 0;
  let deleted = 0;

  for (let i = 0; i < ops.length; i++) {
    const op = ops[i];

    if (op.mark === "equal") {
      for (const block of op.blocks) {
        lines.push({ mark: "equal", depth: block.depth, kind: block.kind, spans: plain(block.text) });
      }
      continue;
    }

    // A deletion immediately followed by an insertion is the shape an *edit*
    // arrives in. Consume both and try to pair the lines up.
    if (op.mark === "delete" && ops[i + 1]?.mark === "insert") {
      const removed = op.blocks;
      const added = ops[i + 1].blocks;
      i += 1;

      const pairs = Math.min(removed.length, added.length);
      for (let p = 0; p < pairs; p++) {
        const line = pairLine(removed[p], added[p]);
        lines.push(line);
        if (line.mark === "changed") {
          changed += 1;
        } else {
          // Not related enough to pair: `pairLine` returns the deletion, and
          // the insertion follows it as its own line.
          lines.push(insertLine(added[p]));
          deleted += 1;
          inserted += 1;
        }
      }
      for (const block of removed.slice(pairs)) {
        lines.push(deleteLine(block));
        deleted += 1;
      }
      for (const block of added.slice(pairs)) {
        lines.push(insertLine(block));
        inserted += 1;
      }
      continue;
    }

    for (const block of op.blocks) {
      if (op.mark === "delete") {
        lines.push(deleteLine(block));
        deleted += 1;
      } else {
        lines.push(insertLine(block));
        inserted += 1;
      }
    }
  }

  return { lines, changed, inserted, deleted };
}

interface LineOp {
  mark: Mark;
  blocks: ReadingBlock[];
}

/**
 * Line-level alignment. Each distinct line text is mapped to one character, so
 * diff-match-patch's character diff becomes a diff over lines — the same
 * `diff_linesToChars_` idea, done explicitly because our "lines" are objects
 * with depth and kind, not substrings of one string.
 */
function alignLines(from: ReadingBlock[], to: ReadingBlock[]): LineOp[] {
  const codes = new Map<string, string>();
  const encode = (block: ReadingBlock): string => {
    // Depth and kind join the key: the same sentence moved to a different
    // level, or demoted from text to a note, is a change worth showing.
    const key = `${block.kind}|${block.depth}|${block.text}`;
    let code = codes.get(key);
    if (code === undefined) {
      code = codePoint(codes.size);
      codes.set(key, code);
    }
    return code;
  };

  const fromCodes = from.map(encode).join("");
  const toCodes = to.map(encode).join("");

  const diffs = engine().diff_main(fromCodes, toCodes, false);

  const ops: LineOp[] = [];
  let fromAt = 0;
  let toAt = 0;
  for (const [op, text] of diffs) {
    const count = text.length;
    if (op === EQUAL) {
      ops.push({ mark: "equal", blocks: to.slice(toAt, toAt + count) });
      fromAt += count;
      toAt += count;
    } else if (op === DELETE) {
      ops.push({ mark: "delete", blocks: from.slice(fromAt, fromAt + count) });
      fromAt += count;
    } else if (op === INSERT) {
      ops.push({ mark: "insert", blocks: to.slice(toAt, toAt + count) });
      toAt += count;
    }
  }
  return ops;
}

/** The nth distinct line, as one character. The surrogate block is stepped
 * over because half a surrogate pair is not a character and diff-match-patch
 * would be free to split one. The ceiling is ~55,000 distinct lines in a
 * single section; the largest in the corpus is three orders of magnitude
 * short of that. */
function codePoint(index: number): string {
  return String.fromCharCode(index < 0xd800 ? index : index + 0x800);
}

/**
 * Word-level, not character-level.
 *
 * A character diff of "$5,000,000" against "$7,500,000" strikes out `5,0` and
 * inserts `7,5`, leaving the reader to reassemble the number in their head.
 * The same encode-to-characters trick that aligns lines aligns words, and the
 * result is what an amendment actually reads like: one figure struck, one
 * inserted.
 */
function wordSpans(before: string, after: string): Span[] {
  const codes = new Map<string, string>();
  const tokensOf = (text: string): string[] => text.match(/\s+|\S+/gu) ?? [];
  const encode = (tokens: string[]): string =>
    tokens
      .map((token) => {
        let code = codes.get(token);
        if (code === undefined) {
          code = codePoint(codes.size);
          codes.set(token, code);
        }
        return code;
      })
      .join("");

  const beforeTokens = tokensOf(before);
  const afterTokens = tokensOf(after);
  const diffs = engine().diff_main(encode(beforeTokens), encode(afterTokens), false);

  const spans: Span[] = [];
  let beforeAt = 0;
  let afterAt = 0;
  for (const [op, text] of diffs) {
    const count = text.length;
    const mark: Mark = op === EQUAL ? "equal" : op === INSERT ? "insert" : "delete";
    const source = op === DELETE ? beforeTokens.slice(beforeAt, beforeAt + count) : afterTokens.slice(afterAt, afterAt + count);
    if (op !== INSERT) beforeAt += count;
    if (op !== DELETE) afterAt += count;

    const chunk = source.join("");
    if (!chunk) continue;
    const last = spans[spans.length - 1];
    if (last && last.mark === mark) last.text += chunk;
    else spans.push({ mark, text: chunk });
  }
  return spans;
}

/** One line edited into another — or, if they have too little in common, just
 * the deletion (the caller adds the insertion after it). */
function pairLine(removed: ReadingBlock, added: ReadingBlock): DiffLine {
  const spans = wordSpans(removed.text, added.text);

  let common = 0;
  for (const span of spans) {
    if (span.mark === "equal") common += span.text.length;
  }
  const longer = Math.max(removed.text.length, added.text.length, 1);
  if (common / longer < PAIR_THRESHOLD) return deleteLine(removed);

  // The line's depth is the one it has *now*; a re-levelled line reads at its
  // new depth, which is what the reader will see on the section page.
  return { mark: "changed", depth: added.depth, kind: added.kind, spans };
}

function insertLine(block: ReadingBlock): DiffLine {
  return { mark: "insert", depth: block.depth, kind: block.kind, spans: [{ mark: "insert", text: block.text }] };
}

function deleteLine(block: ReadingBlock): DiffLine {
  return { mark: "delete", depth: block.depth, kind: block.kind, spans: [{ mark: "delete", text: block.text }] };
}

function plain(text: string): Span[] {
  return [{ mark: "equal", text }];
}

/**
 * "3 lines changed, 1 line added" — the shape of the amendment, before the
 * reader starts reading it. "No changes" when nothing did, which is the whole
 * of what the top line says; when `sourceDelta` found the stored XML differing
 * anyway, the paragraph under it points at the source redline.
 *
 * Every part carries its unit. Naming it once and letting the rest inherit gave
 * "2 added" on a section that had only gained text, which is a count of
 * nothing in particular.
 */
export function diffSummary(diff: DocumentDiff): string {
  const parts: string[] = [];
  const lines = (n: number) => `${n} line${n === 1 ? "" : "s"}`;
  if (diff.changed) parts.push(`${lines(diff.changed)} changed`);
  if (diff.inserted) parts.push(`${lines(diff.inserted)} added`);
  if (diff.deleted) parts.push(`${lines(diff.deleted)} removed`);
  return parts.length > 0 ? parts.join(", ") : "No changes";
}

/**
 * The redline as HTML. Every span is escaped exactly the way a rendered text
 * node is: the input here is statutory text pulled out of XML, and it reaches
 * the page through `set:html`.
 */
export function diffLinesHtml(lines: DiffLine[]): string {
  return lines
    .map((line) => {
      const classes = ["diff-line", `diff-line--${line.mark}`];
      if (line.kind === "note") classes.push("diff-line--note");
      const inner = line.spans
        .map((span) => {
          const text = escapeHtml(span.text);
          if (span.mark === "insert") return `<ins>${text}</ins>`;
          if (span.mark === "delete") return `<del>${text}</del>`;
          return text;
        })
        .join("");
      // `--depth` rather than a class per level: the outline goes as deep as
      // USLM allows, and `site.scss` already owns the step size.
      return `<p class="${classes.join(" ")}" style="--depth: ${line.depth - 1}">${inner}</p>`;
    })
    .join("");
}

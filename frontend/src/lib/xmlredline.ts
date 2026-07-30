/**
 * The source-level redline, rendered in the reader instead of linked away from
 * it.
 *
 * ADR-0026 moved the *reader's* diff onto the reading text, for good reasons
 * that have not changed: a redline of raw USLM for an untouched section is
 * hundreds of regenerated `@id` attributes and no changed words. But "not the
 * default" is not the same as "not available", and the page's answer used to be
 * a link to `/api/v1/…/diff`, which serves JSON — so a reader who wanted the
 * bytes got a wall of `{"op": "equal", "text": …}` in a browser tab.
 *
 * This renders the same comparison as HTML a person can read, in the page.
 *
 * ## Why it does not call the API
 *
 * The diff page already fetches both fragments to build the reading redline, so
 * both texts are in hand — and diff-match-patch is already a dependency here
 * (`diffdoc.ts`). Calling `/api/v1/sections/{id}/diff` would compute the same
 * thing twice and spend the tightest rate limit in the project doing it
 * (ADR-0029 gives that route a burst of 5 and 12/minute, sized for *a person*
 * precisely because nothing server-side was calling it). Doing it locally keeps
 * that true.
 *
 * ## Why it is opt-in
 *
 * It is genuinely expensive — the load test measured the API's version at
 * ~0.45 rps — and Node runs one event loop. So the page computes this only when
 * `?source=1` asks for it, which is also why the toggle is a link rather than a
 * client-side disclosure widget: not rendering it is the point.
 *
 * ## Faithfulness
 *
 * The diff is over the **raw bytes**, not a pretty-printed form of them.
 * Reformatting both sides before diffing would read more nicely and would lie:
 * whitespace is exactly the kind of change this view exists to be able to show,
 * and ADR-0026 names "cannot see a whitespace-only change" as the reading
 * redline's cost. Legibility comes from wrapping and from colouring the markup
 * after the fact, never from changing what is compared.
 */

import DiffMatchPatch from "diff-match-patch";

import { escapeHtml } from "./uslm";

const INSERT = 1;
const DELETE = -1;

export interface SourceRedline {
  html: string;
  /** Characters added and removed — the size of the change, for a reader
   *  deciding whether to expand it. */
  inserted: number;
  deleted: number;
}

/**
 * Colour the markup inside an already-escaped run of XML.
 *
 * Operates on escaped text (`&lt;section …&gt;`), so it can never introduce a
 * tag: everything it wraps was inert before it ran, and the only elements it
 * adds are its own `<span>`s. Attribute *values* are highlighted separately
 * from names because `@id` churn is most of what this view shows, and being
 * able to see at a glance that the change is confined to quoted values is the
 * difference between "the law changed" and "the guids regenerated".
 */
function paintMarkup(escaped: string): string {
  return escaped.replace(/&lt;\/?[^&]*?&gt;/gu, (tag) => {
    const inner = tag.replace(
      /([\w:.-]+)=(&quot;|")(.*?)\2/gu,
      (_match, name: string, quote: string, value: string) =>
        `<span class="xml-attr">${name}</span>=<span class="xml-val">${quote}${value}${quote}</span>`,
    );
    return `<span class="xml-tag">${inner}</span>`;
  });
}

/**
 * A redline of two verbatim XML fragments.
 *
 * `Diff_Timeout = 0` for the same reason `api/diff.py` and `diffdoc.ts` set it:
 * diff-match-patch silently returns a *worse* diff once it times out
 * (`docs/prior-art.md`), and a redline that is subtly wrong is the one failure
 * mode this view cannot have.
 */
export function sourceRedline(before: string, after: string): SourceRedline {
  const dmp = new DiffMatchPatch();
  dmp.Diff_Timeout = 0;

  const diffs = dmp.diff_main(before, after);
  dmp.diff_cleanupSemantic(diffs);

  let inserted = 0;
  let deleted = 0;

  const html = diffs
    .map(([op, text]: [number, string]) => {
      const painted = paintMarkup(escapeHtml(text));
      if (op === INSERT) {
        inserted += text.length;
        return `<ins>${painted}</ins>`;
      }
      if (op === DELETE) {
        deleted += text.length;
        return `<del>${painted}</del>`;
      }
      return painted;
    })
    .join("");

  return { html, inserted, deleted };
}

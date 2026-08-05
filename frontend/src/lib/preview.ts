/**
 * How much of a section a hover preview shows, and where it stops.
 *
 * Separate from the route that uses it (`pages/preview/[...identifier].astro`)
 * because truncating HTML is the part with edge cases, and edge cases belong in
 * Vitest rather than in a page nothing can import.
 */

/** The transfer budget for one preview, in rendered characters.
 *
 * Counted in characters rather than elements because a section can open with
 * one 3,000-character paragraph or with twelve short ones, and the reader's
 * question — "what does this actually say?" — is answered by roughly the same
 * amount of text either way.
 *
 * 4,000 and not 1,400, which is where this started. 1,400 characters of markup
 * is roughly a paragraph and a half of statutory text — less than the card's own
 * 22rem can display, which made the scroll affordance decorative and, worse,
 * usually cut off before the reader could tell whether the cited provision
 * mattered. A preview that cannot answer that is a tooltip with extra steps.
 * 4 KB is nothing on the wire and about a screenful and a half to scroll. */
export const PREVIEW_CHARS = 4000;

/**
 * The placeholder `previewFailureHtml` leaves where the citation's URL goes.
 *
 * The card is built here, on the server, and used in two places: `/app/design`
 * renders it directly, and `CitePreview`'s island — which is `is:inline` and so
 * can import nothing — receives it as a string and substitutes the href of
 * whichever reference failed. One token, one `replaceAll`, one copy of the
 * markup.
 */
export const PREVIEW_HREF = "%HREF%";

/**
 * What the hover card says when the fragment could not be fetched.
 *
 * Never nothing. A card that silently declines to open is indistinguishable
 * from a feature that is broken, or from a citation with no text behind it, and
 * the reader is left with no next step. This names the failure and offers the
 * link (ADR-0041).
 *
 * 429 is called out by name because the preview endpoint is rate-limited per
 * caller (ADR-0029) and a reader working down a dense section will meet it —
 * "too many previews just now" is a wait, where "unavailable" reads as broken.
 */
export function previewFailureHtml(href: string, status?: number): string {
  const reason =
    status === 429
      ? "Preview unavailable — too many previews just now."
      : "Preview unavailable.";
  return (
    `<p class="cite-preview__note">${reason}</p>` +
    `<p class="cite-preview__foot"><a href="${href}">Open the citation →</a></p>`
  );
}

/** Splits rendered HTML into top-level chunks: whole elements, void elements,
 * and runs of text. Non-greedy on the body, anchored on a backreference to the
 * opening tag name, so a `<div>` containing `<div>` is one chunk. */
const CHUNK = /<([a-zA-Z][\w-]*)\b[^>]*>[\s\S]*?<\/\1>|<[^>]+\/?>|[^<]+/gu;

export interface Truncated {
  html: string;
  truncated: boolean;
}

/**
 * Cut rendered HTML down to `limit`, **never inside a tag**.
 *
 * That constraint is the whole difficulty. `html.slice(0, 1400)` will happily
 * cut `<a href="/app/us/…` in half, and the browser then does something
 * inventive with the remainder — usually swallowing the rest of the card as an
 * attribute value. So whole top-level chunks are kept until the budget is
 * spent.
 *
 * The trade is that one enormous opening paragraph overshoots the budget rather
 * than being chopped: correct markup beats an exact byte count, and the card
 * scrolls either way.
 */
export function truncateFragment(html: string, limit: number = PREVIEW_CHARS): Truncated {
  if (html.length <= limit) return { html, truncated: false };

  const parts = html.match(CHUNK);
  // No recognisable structure at all — bail out rather than guess where a tag
  // might be. Returning the input whole is safe; returning half of it is not.
  if (!parts) return { html, truncated: false };

  let kept = "";
  for (const part of parts) {
    if (kept.length > 0 && kept.length + part.length > limit) break;
    kept += part;
    if (kept.length >= limit) break;
  }
  return { html: kept, truncated: kept.length < html.length };
}

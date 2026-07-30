/**
 * What one search box does with what you typed.
 *
 * The header used to carry two boxes side by side — a citation jump and a
 * keyword search — which is two decisions asked of a reader who has one
 * question, and at narrow widths it was also two unusable slivers sharing a
 * row. There is now one box, and this module is the rule it routes by.
 *
 * The rule, in order:
 *
 *   1. **`cites …`** — an explicit request for "what cites this", answered for
 *      now by a keyword search over the cited provision's text. It is a
 *      *prefix* keyword rather than a checkbox because the box has to stay a
 *      plain GET form (no JavaScript, ADR-0023), and a word you type is the
 *      only control a text input has. See `docs/citation-index-plan.md` for the
 *      reverse index this becomes.
 *   2. **Anything that parses as a citation** — a lookup. Decided by
 *      `citeparse.py` behind `GET /api/v1/citation`, never here: the parser
 *      accepts 84 forms and is the single source of truth for what a citation
 *      is (ADR-0023). This module cannot and must not guess.
 *   3. **Everything else** — a keyword search.
 *
 * So the only thing decidable without the API is (1), which is what lives here.
 */

/** The prefix that means "find provisions citing this one". */
export const CITES_KEYWORD = "cites";

export interface CitesQuery {
  /** What was asked about — the citation, with the keyword removed. */
  subject: string;
}

/**
 * `"cites 26 usc 501"` → `{ subject: "26 usc 501" }`; anything else → `null`.
 *
 * Case-insensitive, and the keyword must be a whole word followed by
 * whitespace: `citespersons` is not a request for a reverse lookup, and
 * `"cites"` alone has no subject to look up, so both fall through to the
 * ordinary rules rather than being caught here.
 */
export function parseCites(raw: string): CitesQuery | null {
  const match = new RegExp(`^${CITES_KEYWORD}\\s+(.+)$`, "iu").exec(raw.trim());
  if (!match) return null;
  const subject = match[1].trim();
  return subject ? { subject } : null;
}

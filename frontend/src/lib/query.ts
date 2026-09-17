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
 *   1b. **`history …`** — the version history of a section rather than its
 *      text (ADR-0084), with an optional `from <date> to <date>` after the
 *      citation. `v` is the short form: `v 16 usc 2201`, `v 16/2201`, and
 *      `v16/2201` with no space when a digit follows. The same shape as
 *      `cites` for the same reason: a word you type is the only control a
 *      text input has. The citation itself is
 *      still the API's to read.
 *   2. **Anything that parses as a citation** — a lookup. Decided by
 *      `citeparse.py` behind `GET /api/v1/citation`, never here: the parser
 *      accepts 84 forms and is the single source of truth for what a citation
 *      is (ADR-0023). This module cannot and must not guess.
 *   3. **Everything else** — a keyword search.
 *
 * So the only things decidable without the API are (1) and (1b), which is what
 * lives here.
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

/** The prefix that means "the version history of this section". */
export const HISTORY_KEYWORD = "history";

/** The short form of `HISTORY_KEYWORD`. */
export const HISTORY_SHORT_KEYWORD = "v";

export interface HistoryQuery {
  /** The prefix as typed, lower-cased: `history` or `v`. */
  keyword: string;
  /** The citation, with the keyword and any date range removed. */
  subject: string;
  /** `MM/DD/YYYY` or `YYYY-MM-DD`, as typed; the API validates the form. */
  from: string | null;
  to: string | null;
}

/** A date as a reader types one: `07/12/2026`, `7/12/2026` or `2026-07-12`. */
const DATE = String.raw`(?:\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})`;

/**
 * `"history 16 usc 45f"` → `{ keyword: "history", subject: "16 usc 45f", from: null, to: null }`;
 * `"history 16 usc 45f from 6/12/2026 to 7/12/2026"` carries the range;
 * `"history 16 usc 45f since 2024-01-01"` is `from` alone, which runs to
 * today. `"v 16/2201"` and `"v16/2201"` read the same as `"history 16/2201"`:
 * the short keyword takes whitespace or a digit after it, so a word that
 * merely starts with `v` is not one. Anything else → `null`.
 *
 * Otherwise the rules of `parseCites`: case-insensitive, a whole word, and a
 * subject to look up. The range is read off the end so a
 * citation containing the word "from" — none does, but the parser is not
 * asked to know that — is left whole.
 */
export function parseHistory(raw: string): HistoryQuery | null {
  const match = new RegExp(
    String.raw`^(${HISTORY_KEYWORD}(?=\s)|${HISTORY_SHORT_KEYWORD}(?=\s|\d))\s*(.+)$`,
    "iu",
  ).exec(raw.trim());
  if (!match) return null;
  const keyword = match[1].toLowerCase();
  let subject = match[2].trim();
  let from: string | null = null;
  let to: string | null = null;

  const range = new RegExp(
    String.raw`^(.*?)\s+(?:from|since|between)\s+(${DATE})(?:\s+(?:to|and|until)\s+(${DATE}))?$`,
    "iu",
  ).exec(subject);
  if (range) {
    subject = range[1].trim();
    from = range[2];
    to = range[3] ?? null;
  }
  return subject ? { keyword, subject, from, to } : null;
}

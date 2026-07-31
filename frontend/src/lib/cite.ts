/**
 * A USLM `@identifier`, written out the way a lawyer writes it.
 *
 * `/us/usc/t16/s45f/c/5` → `16 U.S.C. § 45f(c)(5)`. That is the whole job, and
 * it is the exact inverse of `citeparse.py`, which turns the second into the
 * first. The two are tested against each other
 * (`tests/test_citation_forms.py` on that side, `frontend/tests/cite.test.ts`
 * on this one) because a round trip that does not close is a copy button that
 * hands someone a citation this site cannot resolve.
 *
 * It lives here, in TypeScript, rather than in the copy island, because the
 * island is `<script is:inline>` and cannot import anything — so the *page*
 * calls this at render time and ships the finished strings in a JSON block.
 * That is not a workaround: it means the formatting is unit-tested rather than
 * being twelve lines of untestable inline JavaScript, and the island is left
 * with nothing to get wrong but the clipboard.
 *
 * Two things it deliberately does not do:
 *
 *   * **It does not name the level of a subdivision.** `(c)(5)` is written as
 *     `(c)(5)`, never "subsection (c), paragraph (5)". USLM's short-form
 *     vocabulary is empty below section (`docs/prior-art.md` §1), so what level
 *     a bare designator sits at is not recoverable from the string — and a
 *     citation that guesses wrong is worse than one that stays literal. This is
 *     the same rule `provisionLabel` in `url.ts` follows.
 *   * **It does not add a release point.** A citation names a provision; which
 *     text of it you were reading is the URL's job, and the copy widget's link
 *     mode carries that instead.
 */

/** `5a` → `5 U.S.C. App.`; anything else → `N U.S.C.` */
function titlePhrase(titleSegment: string): string {
  const appendix = /^(\d+)a$/iu.exec(titleSegment);
  if (appendix) return `${appendix[1]} U.S.C. App.`;
  return `${titleSegment} U.S.C.`;
}

/** The structural levels an identifier can name, spelled as a citation spells
 * them. Keys are the identifier's own abbreviations (`citeparse._LEVELS`). */
const LEVEL_WORDS: Record<string, string> = {
  ch: "ch.",
  sch: "subch.",
  pt: "pt.",
  spt: "subpt.",
  stI: "subtit.",
  d: "div.",
  sd: "subdiv.",
};

/** Longest prefix first, so `schII` is a subchapter and not a chapter — and, in
 * particular, not a *section* called `chII`, which is what a section-shaped
 * `^s(.+)` test finds if it is allowed to run first. */
const LEVEL_PREFIXES = Object.keys(LEVEL_WORDS).sort((a, b) => b.length - a.length);

/** `schII` → `["sch", "II"]`, `s523` → null. Case-sensitive on the prefix:
 * identifiers write these in a fixed spelling, and matching case-insensitively
 * is how `[a-z]+/iu` swallowed `schII` whole. */
function splitLevel(head: string): [string, string] | null {
  for (const prefix of LEVEL_PREFIXES) {
    if (head.startsWith(prefix) && head.length > prefix.length) {
      return [prefix, head.slice(prefix.length)];
    }
  }
  return null;
}

/**
 * Write an identifier as a citation.
 *
 * Returns the identifier unchanged if it is not one this function recognises —
 * an unreadable citation would be a silent wrong answer on the clipboard, and
 * the raw identifier is at least true and still resolves in the search box.
 */
export function formatCitation(identifier: string): string {
  const match = /^\/us\/usc\/t([0-9]+[a-z]?)(\/.*)?$/iu.exec(identifier);
  if (!match) return identifier;

  const title = titlePhrase(match[1]);
  const rest = (match[2] ?? "").split("/").filter(Boolean);
  if (rest.length === 0) return `Title ${match[1]}, U.S. Code`;

  const [head, ...tail] = rest;

  // Levels before sections: `sch` and `spt` both begin with the `s` a section
  // begins with, so a section-shaped test run first reads `/schII` as a section
  // numbered `chII`.
  const level = splitLevel(head);
  if (level) return `${title} ${LEVEL_WORDS[level[0]]} ${level[1]}`;

  const section = /^s(.+)$/u.exec(head);
  if (section) {
    const subdivisions = tail.map((segment) => `(${segment})`).join("");
    return `${title} § ${section[1]}${subdivisions}`;
  }

  return identifier;
}

/** What a copy target needs, computed once on the server. */
export interface CopyTarget {
  /** The USLM `@identifier`, which is also the element's `id` in the page. */
  identifier: string;
  /** `16 U.S.C. § 45f(c)(5)`. */
  cite: string;
  /** The reader URL for it, relative — the island makes it absolute against
   * `location.origin`, which is the only part that cannot be known here. */
  href: string;
}

/**
 * The search operators this site supports — the single list the guide renders.
 *
 * This exists because a syntax guide is a promise, and a promise about a query
 * parser is exactly the kind that rots. `api/search.py` enables a named set of
 * `simple_query_string` flags; every operator below is one of them, and
 * `tests/test_search_syntax.py` reads both this file and that constant and
 * fails if they disagree. A flag dropped from the API without a change here
 * would otherwise leave the guide describing an operator the cluster silently
 * treats as a literal character — which is worse than no guide, because the
 * reader would have no way to tell the difference from a query that legitimately
 * found nothing.
 *
 * The `flag` values are Lucene's `SimpleQueryParser` flag names, not names
 * invented here.
 */

export interface SearchOperator {
  /** The `simple_query_string` flag that enables it. Matched against
   * `api.search.QUERY_SYNTAX_FLAGS`.
   *
   * Absent on an operator this site implements itself rather than passing to
   * the cluster — the `field:value` scopes, which carry `scope` instead. */
  flag?: string;
  /** The name `storage/searchquery.py` parses this prefix under. Matched
   * against `SCOPE_FIELDS` and `TIME_SCOPES` there, so a scope documented here
   * and unknown to the parser fails the build the same way a missing flag
   * does. */
  scope?: string;
  /** How it is written, for the table's first column. */
  syntax: string;
  /** A short name for what it does. */
  name: string;
  /** A query a reader can click, chosen to actually demonstrate the operator
   * against the real corpus rather than to read well. */
  example: string;
  /** What the example does, and — where it matters — what it does *not* do. */
  explanation: string;
}

/**
 * Rewrite a query so every plain word tolerates one character edit.
 *
 * This is the "did you mean" offer on a search that found nothing — the escape
 * hatch for the strictness ADR-0031 introduced. It has to append `~1` to *each*
 * word, not to the query: `water polution~1` fuzzes only the second word, which
 * is exactly the case where the reader mistyped the first one.
 *
 * Words already carrying syntax are left alone. Appending `~1` to `"a phrase"`
 * would silently change it into a proximity search, and to `word*` would
 * produce `word*~1`, which is not a thing — in both cases the reader would get
 * a different query than the one they are being offered.
 */
export function fuzzify(query: string): string {
  return query
    .split(/\s+/u)
    .filter(Boolean)
    .map((term) => (/[~*"()|+\\-]/u.test(term) ? term : `${term}~1`))
    .join(" ");
}

export const SEARCH_OPERATORS: SearchOperator[] = [
  {
    flag: "PHRASE",
    syntax: '"…"',
    name: "Exact phrase",
    example: '"navigable waters"',
    explanation:
      "The words in that order, next to each other. Without the quotes both words must still appear, but anywhere in the provision and in any order.",
  },
  {
    flag: "FUZZY",
    syntax: "~n",
    name: "Misspellings",
    example: "conservation~1",
    explanation:
      "Also matches words within n single-character edits — one insertion, deletion, substitution or transposition each. Use it when you are unsure of a spelling. Keep n at 1 or 2: at 2, six-letter words start matching genuinely unrelated ones.",
  },
  {
    flag: "PREFIX",
    syntax: "*",
    name: "Word beginning",
    example: "navigab*",
    explanation:
      "Matches any word starting with those letters — navigable, navigability, navigation. Only at the end of a word; a leading * is not supported, because matching every word by its ending would mean scanning the whole index.",
  },
  {
    flag: "SLOP",
    syntax: '"…"~n',
    name: "Words near each other",
    example: '"secretary interior"~3',
    explanation:
      "The phrase, but allowing up to n words in between and in either order. Useful when you know two terms belong together but not exactly how they are written.",
  },
  {
    flag: "NOT",
    syntax: "-",
    name: "Exclude",
    example: "water -pollution",
    explanation:
      "Excludes provisions containing the word. The minus goes immediately before the word, with no space after it.",
  },
  {
    flag: "AND",
    syntax: "+",
    name: "Require",
    example: "+wildlife +refuge",
    explanation:
      "Requires the word. Rarely needed here, because every word is already required by default — it matters only when you have written an | somewhere in the same query.",
  },
  {
    flag: "OR",
    syntax: "|",
    name: "Either word",
    example: "forest | grassland",
    explanation:
      "Matches provisions containing either word. Use it to loosen a search that is finding too little.",
  },
  {
    flag: "PRECEDENCE",
    syntax: "( )",
    name: "Grouping",
    example: "(forest | grassland) -timber",
    explanation:
      "Groups terms so the operators apply the way you meant, exactly as in arithmetic.",
  },
  {
    flag: "ESCAPE",
    syntax: "\\",
    name: "Literal character",
    example: "\\-",
    explanation:
      "Treats the next character as text rather than as an operator — for searching a phrase that genuinely contains a hyphen or a quotation mark.",
  },
  {
    flag: "WHITESPACE",
    syntax: " ",
    name: "Space",
    example: "public lands",
    explanation:
      "A space separates terms, and all of them must be present. This is the default, so every word you add narrows the search.",
  },
  {
    scope: "heading",
    syntax: "heading:",
    name: "In the heading only",
    example: "heading:conservation",
    explanation:
      "Matches the word in a section's heading rather than anywhere in its text. Use quotes for more than one word: heading:\"wild horses\".",
  },
  {
    scope: "title",
    syntax: "title:",
    name: "One title",
    example: "conservation title:16",
    explanation:
      "Restricts the search to that title of the Code. Written either way — title:16 or title:t16. Repeat it for several titles, which matches any of them.",
  },
  {
    scope: "chapter",
    syntax: "chapter:",
    name: "One chapter",
    example: "conservation title:16 chapter:1",
    explanation:
      "Restricts the search to that chapter number. Chapter numbers repeat across titles, so pair it with title: unless you mean chapter 1 of every title.",
  },
  {
    scope: "status",
    syntax: "status:",
    name: "Repealed, omitted, transferred",
    example: "conservation status:repealed",
    explanation:
      "Restricts the search to provisions carrying that status. status:none is the rest — the sections the source marks with no status at all, which is most of the Code.",
  },
  {
    scope: "release",
    syntax: "release:",
    name: "At a release point",
    example: "conservation release:119-99",
    explanation:
      "Searches the text as it stood at that release point instead of the text in force. The same thing ?release= does, written in the box.",
  },
  {
    scope: "date",
    syntax: "date:",
    name: "At a date",
    example: "conservation date:05/08/2026",
    explanation:
      "Searches the text in force on that date, resolved to the release point current then. ?release= wins if both are given.",
  },
];

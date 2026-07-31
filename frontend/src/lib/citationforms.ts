/**
 * The citation forms the header's one box accepts — the list the guide renders.
 *
 * Same contract, and the same reason for existing, as `searchsyntax.ts`: a
 * guide is a promise, and a promise about a parser is the kind that rots
 * silently. `citeparse.py` is the only thing that decides what a citation *is*
 * (ADR-0023); every row below names an example and the `@identifier` that
 * example must produce, and `tests/test_citation_forms.py` runs each one
 * through the real parser and fails if any disagrees.
 *
 * That test is the point of the file. Documenting "we accept the inverted form"
 * costs nothing and proves nothing; documenting that `Section 14123(a)(2), 49
 * U.S.C.` resolves to `/us/usc/t49/s14123/a/2` is checkable, and it is checked.
 *
 * Two things the table has to say out loud because they are the two ways a
 * correct-looking citation lands nowhere:
 *
 *   * **Subdivision case is preserved.** `(B)` becomes `/B`, never `/b` — USLM
 *     identifiers distinguish them.
 *   * **A section number can hold an en dash.** OLRC writes `45a–1` with U+2013,
 *     and 5,697 of the corpus's 65,938 sections contain one while not a single
 *     one contains a plain hyphen (CLAUDE.md gotcha 17). No keyboard has that
 *     key, so the parser produces both spellings and the lookup tries each.
 */

export interface CitationForm {
  /** Short name for the shape, for the row's heading. */
  name: string;
  /** A citation a reader can click. Must parse to `identifier`. */
  example: string;
  /** The `@identifier` `citeparse.parse_citation` produces for `example`. */
  identifier: string;
  /** What the parser made of it, and what is worth knowing about the shape. */
  explanation: string;
}

/** Forms that resolve. Ordered by how likely someone is to type them. */
export const CITATION_FORMS: CitationForm[] = [
  {
    name: "The standard citation",
    example: "11 U.S.C. § 523",
    identifier: "/us/usc/t11/s523",
    explanation:
      "Title, U.S.C., section. The section symbol is optional, so is every period, and so is the spacing: 11 usc 523 and 11 U. S. C. 523 are the same citation.",
  },
  {
    name: "Down to a subdivision",
    example: "11 U.S.C. § 523(a)(1)(B)(ii)",
    identifier: "/us/usc/t11/s523/a/1/B/ii",
    explanation:
      "Parentheses become path segments, as deep as you write them. Case is kept: (B) is not (b), because the official identifiers distinguish the two.",
  },
  {
    name: "A section number that is not a number",
    example: "16 usc 45f(c)(5)",
    identifier: "/us/usc/t16/s45f/c/5",
    explanation:
      "Section numbers carry letters — 45f, 1a, 78j-1 — and are matched as written rather than as an integer.",
  },
  {
    name: "A hyphenated section number",
    example: "42 USC 2000e-2",
    identifier: "/us/usc/t42/s2000e-2",
    explanation:
      "Type the hyphen your keyboard has. The official text writes these with an en dash (45a–1, U+2013), so both spellings are tried and whichever exists is what you land on.",
  },
  {
    name: "The inverted form",
    example: "section 523 of title 11",
    identifier: "/us/usc/t11/s523",
    explanation:
      "The way a statute refers to itself in prose. Sec., §, and a subdivision all work here too: Sec. 523(a) of Title 11.",
  },
  {
    name: "Title last",
    example: "Section 14123(a)(2), 49 U.S.C.",
    identifier: "/us/usc/t49/s14123/a/2",
    explanation:
      "The abbreviated inverted form used in the Office of the Law Revision Counsel's own notes.",
  },
  {
    name: "Title and section, nothing else",
    example: "11/523",
    identifier: "/us/usc/t11/s523",
    explanation:
      "The fastest thing to type. Subdivisions follow as slashes: 11/523/a/1.",
  },
  {
    name: "The identifier itself",
    example: "/us/usc/t16/s45f/c/5",
    identifier: "/us/usc/t16/s45f/c/5",
    explanation:
      "The official USLM @identifier, pasted straight in — which is also this site's URL scheme, so a URL from anywhere on the site works in the box. Fragments of one do too: t16/s45f.",
  },
  {
    name: "A chapter or other level",
    example: "11 usc ch. 5",
    identifier: "/us/usc/t11/ch5",
    explanation:
      "Chapters, subchapters, parts, subparts and subtitles, spelled out or abbreviated. This lands on that level's table of contents rather than on a section.",
  },
  {
    name: "A level, written the long way",
    example: "title 11, chapter 5",
    identifier: "/us/usc/t11/ch5",
    explanation: "The same destination, in the form prose tends to use.",
  },
  {
    name: "A whole title",
    example: "title 11",
    identifier: "/us/usc/t11",
    explanation:
      "The title's table of contents. 11 usc, with nothing after it, means the same thing.",
  },
  {
    name: "A note",
    example: "11 usc 523 note",
    identifier: "/us/usc/t11/s523",
    explanation:
      "The trailing note is recognised and you land on the section, whose notes are on the page. This site serves no separate route for notes, so the word is read and then set aside rather than ignored.",
  },
  {
    name: "A run of sections",
    example: "16 usc 45f et seq.",
    identifier: "/us/usc/t16/s45f",
    explanation:
      "et seq. names a run starting at a section. You land at its start; there is no view of a range as such.",
  },
  {
    name: "Wrapped in brackets",
    example: "(11 U.S.C. 523)",
    identifier: "/us/usc/t11/s523",
    explanation:
      "Enclosing brackets, quotes and trailing punctuation are stripped, so a citation pasted out of the middle of a sentence works. Brackets that belong to the citation are kept — 523(a)(1) is not mistaken for one of these.",
  },
];

/**
 * Forms that parse and then resolve to nothing, and forms that do not parse at
 * all. Documented because each one looks like a bug from the outside, and each
 * is a decision.
 */
export interface CitationLimit {
  example: string;
  /** The identifier it parses to, or null when it does not parse. */
  identifier: string | null;
  explanation: string;
}

export const CITATION_LIMITS: CitationLimit[] = [
  {
    example: "523",
    identifier: null,
    explanation:
      "A section number with no title is unresolvable — there is a § 523 in many titles — and guessing would be worse than asking. Typed on its own it is treated as a word and searched for.",
  },
  {
    example: "5 U.S.C. App. 3",
    identifier: "/us/usc/t5a/s3",
    explanation:
      "Appendix citations parse and then find nothing. The five appendix titles are published under the enacting instrument rather than a flat section number — 0 of 461 appendix sections use this shape; they look like /us/usc/t5a/pl/92/463/s1. Getting from one to the other needs a lookup table this site does not have, so it says so rather than inventing one.",
  },
];

# ADR-0026 — The reader's diff is a redline of the reading text, not of the XML

- **Status:** Accepted (amends ADR-0016, which stands for the API)
- **Date:** 2026-07-30
- **Context:** Session 11, BUILDLOG 025

## Context

ADR-0016 built the diff as a source-level redline: `api/diff.py` diffs two
verbatim USLM fragments with diff-match-patch, and `/app/diff/…` escaped those
ops and printed them. The ADR named the simplification out loud — "a diff of the
raw XML, not of the rendered reading text" — and it was the right first move,
because it needed no USLM vocabulary at all and therefore could live in `api/`
without breaking architecture rule 5.

What it produces in front of a reader is this:

```
<section identifier="/us/usc/t16/s45f" id="id0b32dff7-810c-11f1-…">
                                       ^^^^^^^^^^^^^^^^^^^^^^^^^ struck
<section identifier="/us/usc/t16/s45f" id="id7944f575-6992-11f1-…">
                                       ^^^^^^^^^^^^^^^^^^^^^^^^^ inserted
```

repeated for every element in the section, because **guids regenerate at every
release point by design** (ADR-0003, gotcha 1). Two facts about that:

- It is not a rendering problem to be tuned. An untouched section's XML differs
  at every RP; the redline of an unchanged section was pages of changes.
- It is measurable. The load test recorded roughly half the diff's cost as `@id`
  churn: diffing the guid-stripped text took 2,220 ms → 1,172 ms and 51 → 20
  ops. That measurement was filed as a debt against the *API*. The reader's
  version of the same problem is worse, because the API's consumer is a program
  and the reader's consumer is a person.

The user-visible complaint was simply: don't show me the markup.

## Decision

**The reader's diff page renders both versions as reading text and diffs
those.** The API is unchanged: `/api/v1/sections/{id}/diff` still serves the
source-level redline, and the page links to it in a footer line, so the bytes
stay one click away and ADR-0016's artifact is not orphaned.

Three consequences of where this had to live:

**1. It is computed in the frontend, not in Python.** Turning a fragment into
the lines a reader reads is a USLM question — `<num>` and its `<chapeau>` are
one line, a nested `<paragraph>` is another, a `<note>`'s `<p>` children are
each their own — and `frontend/src/lib/uslm.ts` is the only module outside the
parsers allowed to ask one (architecture rule 5). Adding a text extractor to
`api/` would have put USLM element names on both sides of the boundary, which is
the rule ADR-0015 exists to protect. So `uslm.readingBlocks()` extracts, and
`lib/diffdoc.ts` diffs.

**2. Two passes, so the output is a document and not a stream.** Lines are
aligned first (each distinct line encoded as one character, then diffed — the
standard line-mode trick), and only then is a deleted line paired with an
inserted line and diffed *word by word*. A character diff of `$5,000,000` against
`$7,500,000` strikes `5,0` and inserts `7,5`; word mode strikes one figure and
inserts the other, which is what an amendment reads like.

**3. An unrelated pair is not shown as an edit.** A deletion followed by an
insertion is only merged into one "changed" line when the two share at least 40%
of the longer line. Below that they render as a deletion and an insertion,
because claiming one sentence "became" an unrelated one is a lie the reader
cannot detect.

`Diff_Timeout = 0` is carried over from `api/diff.py` for the reason
`docs/prior-art.md` records: diff-match-patch silently returns a *worse* diff
once it times out, and a subtly wrong redline is the one failure this view
cannot have.

## Consequences

- **The headline case now reads correctly.** Two release points of an untouched
  section produce "The text of this section is identical at both release
  points." — instead of hundreds of guid ops. There is a unit test that asserts
  exactly this, built from two fragments that differ only in `@id`.
- **The reader stops calling `/sections/{id}/diff`** and fetches the two
  sections instead. The CPU moves from the API process to the Astro process. It
  is also less CPU: the reading text is smaller than the XML and free of the
  churn that dominated the old diff. The standing debt — *the API's diff
  endpoint is unauthenticated and CPU-bound and must be rate-limited before the
  URL is advertised* — is unchanged and still owed.
- **One npm dependency, `diff-match-patch`**, server-side only (SSR); no
  browser bundle grows. It is the same algorithm and the same author as the
  Python package already in use, which keeps the two redlines comparable rather
  than merely similar.
- **Structure is preserved as indentation, not as markup.** Each line carries
  its outline depth as a CSS custom property. Notes and source credit are marked
  as apparatus and rendered quieter than statutory text — they belong in the
  redline (they change, and readers ask why) but they are not the law.
- **Whitespace is normalized before diffing**, so a reflowed source line is not
  a change. The cost is that a genuine whitespace-only change is invisible;
  between two release points of a statute that is the right trade.
- **What is lost:** the rendered redline drops the `<ref>` links, so a changed
  cross-reference is text rather than a hyperlink with a hover preview. Worth
  revisiting; not worth blocking on, since the section pages either side of the
  diff have both.

## Alternatives considered

- **Rendering the API's XML ops.** The ops are contiguous slices of the two XML
  strings, so both documents can be reconstructed — but marking an insertion
  inside the *rendered* output means injecting sentinels into the XML at op
  boundaries, and a boundary can fall inside a tag. Fragile in exactly the way a
  legal redline must not be.
- **Diffing rendered text in Python.** Requires a second USLM renderer on the
  API side. Rejected on architecture rule 5, and on the duplication.
- **Keeping the XML redline and hiding `@id` before diffing.** This is the debt
  already filed against ADR-0016, and it fixes the *cost* without fixing what
  the page shows: the reader still gets tags.
- **A dependency-free diff.** A word LCS is fine for a paragraph and quadratic
  for a section. Myers via diff-match-patch is one small server-side package
  against a whole class of pathological inputs.

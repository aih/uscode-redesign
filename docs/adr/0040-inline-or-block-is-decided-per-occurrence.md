# ADR-0040: Inline or block is decided per occurrence, from a measurement

**Status:** Accepted
**Date:** 2026-08-04
**Related:** [ADR-0011](0011-astro-uswds-frontend-at-app.md) (the renderer this changes),
[ADR-0026](0026-diff-the-reading-text-not-the-xml.md) (the redline, which reads the same partition),
[ADR-0033](0033-copy-column-four-modes.md) (the copy control, which decides line breaks by whether a
node is a block), [ADR-0039](0039-accessibility-is-a-ratchet-in-the-browser-suite.md) (WCAG 1.3.2 is
why this is a defect rather than a cosmetic preference)

## Context

`frontend/src/lib/uslm.ts` sorted USLM elements into inline and block by name, with a `<div>`
fallback for everything it did not name. Two things were wrong with that.

The list was written from memory. `<date>` was not on it, so every date in every editorial note
rendered as a `<div>` in the middle of its sentence — 20,513 occurrences in the Title 16 sample
alone, and not one of them anywhere but inside running prose. This was a known debt in CLAUDE.md
("one entry in `uslm.ts`'s inline set, left out of a scoped refresh") and it had been read as a
formatting nuisance. It is WCAG 1.3.2: a block reorders the sequence a screen reader announces,
mid-sentence, in the part of the page a drafter reads for amendment history.

The deeper problem is that a name is not always enough. `<note>` is an editorial note 30,981 times
and a footnote marker inside a sentence 883 times. `<quotedContent>` is a block quotation 875 times
and a quoted phrase inside a sentence 2,701 times. Neither can be classified by name at all, and
whichever way it is classified, the other few thousand occurrences are wrong.

## Decision

**The partition is measured, not remembered, and elements the source uses both ways are decided per
occurrence.**

1. `scripts/inline_elements.py` counts, for every element across the committed USLM 1.x and 2.x
   samples, how often it sits beside a non-whitespace text node. That is the empirical definition of
   "in running prose", and it is the same question the renderer has to answer.
   `docs/verification/inline-elements.json` is the result.

2. Elements that occur in prose and never otherwise join `INLINE_TAGS`: `date` (20,513 / 0) and
   `footnote` (1,051 / 0).

3. Elements the source uses both ways are in `CONTEXTUAL_TAGS`, and `inRunningProse(el)` asks the
   markup at render time — a non-whitespace text node immediately before or after. The inline case
   is marked `.uslm-inlined`, which cancels the block box in CSS.

4. `tests/uslm.test.ts` reads the artifact and asserts, element by element, that nothing it found in
   prose renders as a `<div>`. Elements that stay blocks are listed there with the ratio that
   justifies each, so the exception is a diff rather than an omission.

The same test runs in `collectBlocks`, which feeds the redline (ADR-0026): a `<note>` left to the
line-break rule flushed, and one sentence redlined as three blocks.

## Where the line is drawn

`<p>` appears beside text 50 times against 58,865 isolated, `<table>` 26 against 796, `<list>` 8
against 36, `<heading>` 3 against 87,187, `<proviso>` 2 against 5. All stay blocks. Under 1% is the
source being odd rather than a content model, and a `<heading>` rendered as a `<span>` would cost the
document outline more than three sentences are worth.

## Costs

**An element's rendering now depends on its siblings.** Two `<note>` elements with identical content
render differently, which is correct and is also a new thing to know when reading the renderer. The
`.uslm-inlined` class makes it visible in the output.

**A `<span>` may contain block children.** A `<quotedContent>` in running prose whose quoted material
has internal structure produces a `<span>` wrapping a `<div>`. Browsers render it; validators will
complain. The alternative — 2,701 quoted phrases each breaking its sentence — is worse.

**The measurement is four files, not 58 titles.** The samples are Title 16 in both schemas, Title 49
and Title 1. An element that only appears in running prose in some title nobody sampled is still
classified by the `<div>` fallback. Re-running the script against a wider sample is the fix, and it
is one command.

**`term` and `quote` were expected and do not exist.** Neither appears in any sample, in either
schema. They are named here so the next person does not go looking.

**The copy control's output changed as a side effect.** `CopyColumn` decides line breaks by whether a
node is a block, so a date inside a note used to break the copied line and no longer does
(ADR-0033).

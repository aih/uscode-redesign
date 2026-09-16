# ADR-0083 — A section absent from a release point shows its last text, with a warning

**Status:** accepted (2026-09-16)

**Task:** When a recent release point does not contain a section, fall back to the most recent
release point that does, and tell the reader to check the most recent release point.

**Amends:** ADR-0065 (whose decision 2 made such a request a 404 that names when the section
existed; it is now an answer).

## Context

A section can leave the Code without a `repealed` marker (gotcha 3). Title 14 was renumbered in
2018 by Pub. L. 115-282: `/us/usc/t14/s1`, "Establishment of Coast Guard", is published at every
release point through 115-384not282not334 and at none after. OLRC also re-cuts ranges of repealed
sections — `/us/usc/t16/s100 to 105` is one identifier at 113-36 and several later. Measured on the
development corpus, **5,152 of 65,938 sections are absent from their title's newest loaded release
point**; title 10 has 1,139, title 20 596, title 42 474, title 14 406.

Until now a request for one of these at a release point that lacks it was a 404 — "nothing at
/us/usc/t14/s1 in release point 119-73" — with ADR-0065's page saying at how many release points
it *is* in the Code. That answer is true and sends the reader away with nothing: a citation to 14
U.S.C. § 1 in a 2015 brief is a real citation to real text, and the text is in the database.

The same shape appeared under ADR-0082's failure: title 42 at 119-102 was loaded and empty, and
every section 404'd. That case is fixed at its root (the serving path ignores an unfinished load).
This decision is about sections that are genuinely gone from a release point that is genuinely
loaded.

## Decision

### 1. Fall back to the most recent release point that contains the section

`get_section` resolves `served_from` as before — the newest completely loaded release point at or
before the request, for the title. If that release point holds no occurrence of the section,
`_last_release_holding()` finds the newest release point *before* it at which the section is
published, and the answer is served from there: that text, that guid, that placement, those
neighbours.

The fallback reaches backward only. A request for a release point before the section first
existed finds nothing older and stays a 404, which ADR-0065's page still explains. "Not yet" and
"no longer" are different answers.

### 2. The answer names the release point that lacks it

`SectionResult.absent_from` carries the release point that would have answered and did not;
`served_from` is the one that did; `is_exact` is false. `/api/v1/us/usc/…` returns `absent_from`
as a release object, and `note` reads:

> /us/usc/t14/s1 is not in the Code at release point 119-73 (2026-01-23). This is its text as
> published at 115-384not282not334 (2018-12-21), the most recent release point that contains it.
> Check the most recent release point for its current status — a section can leave the Code by
> being renumbered or transferred without being marked repealed.

The reader renders it as a warning alert above the text, with a link to the title at the most
recent release point and to the section's former parent. The release bar's served-from note is
suppressed on that page so the fact is stated once.

### 3. The cache policy follows `is_exact`

An unpinned request whose answer is a fallback revalidates every five minutes, as an unpinned
answer always has. A pinned older release point at which the section is absent is also
`is_exact: false`, so it is not cached immutably either — conservative, since a corpus load
cannot put a section into a release point it was not published at.

## Consequences

**A vanished section reads as present.** A reader who lands on 14 U.S.C. § 1 sees a section page
with text on it. The warning is the whole of the difference, and it is above the text, in the
alert style, with the reason. A reader who skips it reads 2018 law under a 2026 release bar — the
bar itself says the release point is not the newest, as it did before.

**`labels` and the hover preview do not fall back.** A cross reference to a vanished section
still gets "not found" from the labels batch, and the preview card fetches the section endpoint
and will show the fallback text with the note. The two disagree at the edge; the batch is a
per-page cost (ADR-0033) and was left alone.

**The 404 page's "in the Code at N release points" is now reached only from the past** — a
request for a release point before the section existed. The prose stays; the case narrows.

**The reader's `/versions` and redline pages are unchanged.** Both already span every release
point the section was published at, and neither ever 404'd for a vanished section.

**Measured cost:** one extra query on the miss path, none on the ordinary path.
`tests/test_api.py` plants a section published at 119-99 alone, since nothing left Title 16
between the fixture's two release points, and asserts the fallback, the exact answer at 119-99,
the 404 before it existed, and that an ordinary section carries no `absent_from`. The guide's
scenario runs against the corpus (`/us/usc/t14/s1`), skipped in CI.

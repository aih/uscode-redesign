# ADR-0016: The diff computes through the Repository; presentation is the frontend's job

**Date:** 2026-07-28 · **Status:** Accepted · **Implements:** Day 4 (PLAN.md)

## Context

`../versions` (`docs/prior-art.md` §2) diffs whole documents client-side, in the browser,
with `@emmetio/xml-diff` wrapping `diff-match-patch` and `Diff_Timeout: 0` — recorded there
as load-bearing, since diff-match-patch silently returns a *worse* diff once it times out.
Day 4 asks for the same feature — a redline between any two versions of a section — and asks
explicitly where it should compute: an `/api/v1/…/diff?from=&to=` endpoint through the
`Repository`, with presentation in the frontend, "element names stay out of `api/`".

## Decision

**The diff is computed in `api/diff.py`, on the two sections' verbatim XML strings, as a
generic text diff.** The route (`GET /api/v1/sections/{id}/diff?from=&to=`) resolves both
release points the same way every other route does, fetches both `SectionResult`s through
`repository.get_section`, and hands their `.xml` to `diff_ops()` — `diff_match_patch.diff_main`
with `Diff_Timeout = 0` and `diff_cleanupSemantic`, the same setting `../versions` used,
ported at the layer that now does the computing. The response is `{identifier, from, to,
ops: [{op, text}]}` — `op` is `equal`/`insert`/`delete`, and `text` is a literal substring
of the XML, never parsed or interpreted.

**This is deliberately not a structural (element-aware) diff.** `@emmetio/xml-diff` aligns
XML trees, not just characters, so an attribute change doesn't smear across surrounding
text. Reproducing that in Python would mean parsing USLM inside `api/` — exactly what
CLAUDE.md architecture rule 5 reserves for `frontend/src/lib/uslm.ts` alone. A plain text
diff over the raw XML needs no element vocabulary at all: it treats the fragment as an
opaque string, so `api/diff.py` stays as ignorant of `<section>`/`<heading>`/`<ref>` as
every other file outside the parsers (`tests/test_architecture.py`'s
`quotedContent` canary covers it too).

**Presentation renders `ops` as an inline redline of the XML source**, not as a diff of the
fully-rendered HTML. `frontend/src/pages/diff/[...identifier].astro` wraps each `insert`
chunk in `<ins>`, each `delete` in `<del>`, escapes the rest, and sets it in a monospace-ish
block (`.diff-view`) next to both release points' labels. This is a source-level diff — akin
to the existing "Source XML" link already on every section page — not a word-level diff of
the reading text. That is a real, named simplification: a change to an `@identifier` or a
`style` attribute shows up as tag-level noise in the redline rather than being invisible. It
was chosen over aligning diff ops back onto the rendered HTML tree (fragile — an arbitrary
substring boundary from a text diff does not respect HTML tag boundaries) and over adding a
second, HTML-aware diff pass in `frontend/src/lib` (real value, but out of scope for Day 4;
left as a follow-up if the source-level view proves too noisy in practice).

## Consequences

- `api/diff.py` has one dependency (`diff-match-patch`, PyPI, MIT — a direct port of the
  same library `../versions` used in JS) and no new architecture-test exception: it imports
  no SQL, no `db.models`, and no element name.
- The diff is bounded by construction (ADR-0001: sections are the storage atom), so
  `Diff_Timeout = 0` costs nothing in practice — a single section's XML, not a whole title.
- If the source-level redline turns out to be too noisy for real use (attribute churn
  drowning out substantive text changes), the fix is additive: a second, frontend-side pass
  that diffs `render()`'s HTML output instead of the raw XML, without touching this endpoint.

# ADR-0005: What counts as a section (and a correction to the Title 16 counts)

**Date:** 2026-07-27 · **Status:** Accepted

## Decision

A `<section>` element is emitted as a `SectionRecord` only when it

1. carries an `@identifier`, and
2. has no `<quotedContent>` ancestor.

Everything else in the file is left in place — in particular, a skipped quoted section is **not** cleared from the tree, because its end event fires *before* the enclosing real section's and the enclosing section's XML must be stored verbatim.

## Why: the published counts were counting the wrong thing

PLAN.md §1 and CLAUDE.md record Title 16 @ `119-102not101` as **5,393 sections; 523 repealed / 102 omitted / 19 transferred / 1 reserved**. Those are raw `grep`-level element counts, and two of them do not survive contact with the data:

| | raw `<section>` elements | real code sections |
|---|---|---|
| total | 5,393 | **5,095** |
| repealed | 523 | **522** |
| omitted | 102 | 102 |
| transferred | 19 | 19 |

**298 of the 5,393 `<section>` elements sit inside `<quotedContent>`** — statutory text quoted by an amending act, reproduced inside another section's notes. None of them has an `@identifier` or an `@id`; one of them is marked `status="repealed"`. They are not provisions of the Code, they have no URL, and storing them as sections would create 298 phantom entries with no identity and duplicate the text of the sections that quote them.

**The single `reserved` is not on a section at all** — it is `<subchapter status="reserved" identifier="/us/usc/t16/ch1/schXCVII">`. Section-level status counts therefore total 643, never 644, and any verification report that expects a reserved *section* in Title 16 will always fail.

Both figures are now asserted from both directions in `tests/test_uslm_full_corpus.py`: the raw element counts (5,393 / 298 / 523 / one reserved subchapter) *and* the emitted counts (5,095 / 522), so the arithmetic connecting them is checked rather than asserted.

## Related decisions recorded here

- **`@status` is a free string, never an enum.** USLM 2.x Title 49 carries `renumbered`, which Title 16 never shows, and CLAUDE.md gotcha 8 predicts more drift in the 2013–2015 release points.
- **`@temporalId` does not exist in USLM 1.0.15 output** — zero occurrences in a 32 MB title. `SectionRecord.temporal_id` is therefore `None` for every current release point. It stays in the record because it is display-only (ADR-0003) and 2.x may populate it.
- **Every `@id` in a section is indexed, not just the section's own.** Title 16 has 63,376 ids against 5,095 sections. Elements such as `<p>` carry an `@id` but no `@identifier`, so a `GuidRef` inherits the nearest enclosing `@identifier` (at minimum the section's). `GET /us/usc/?id=` then resolves *any* guid in the corpus to a retrievable provision, which is what PLAN.md §3's global `guid_map` promises.
- **Document order is preserved and nothing is skipped.** `seq` is a contiguous 0-based counter over emitted sections, so repealed and omitted sections keep their place in prev/next (CLAUDE.md gotcha 9).

## Consequences

CLAUDE.md and PLAN.md are updated to carry both numbers with the distinction spelled out, because the raw counts are what someone re-deriving them with `grep` will see first. The `make verify` full-corpus report (PLAN.md §11.5, Day 7) must compare against the **emitted** counts and report the raw ones alongside.

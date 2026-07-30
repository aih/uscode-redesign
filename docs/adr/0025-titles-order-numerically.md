# ADR-0025 — Titles order numerically, and the ordering is the Repository's contract

- **Status:** Accepted
- **Date:** 2026-07-29
- **Context:** Session 10 (UI refresh before deploy), BUILDLOG 024

## Context

The front page listed the Code like this:

```
Title 1, Title 10, Title 11, Title 11a, Title 12, … Title 2, Title 20, …
Title 5, Title 50, Title 50a, Title 51, Title 52, Title 54, Title 5a, …
```

It is the first thing a visitor sees, and it had been wrong since the titles list
was built. The cause is one clause in `PostgresRepository.list_titles`:

```python
for title in self._session.scalars(select(Title).order_by(Title.num))
```

`Title.num` is a `String` column, and correctly so: **`5a` is a title number and
`5` is a different title.** The five appendix titles (`5a`, `11a`, `18a`, `28a`,
`50a`) are separate files with separate content (gotcha 7), so the column cannot
be an integer and the number cannot be normalised away. What follows is that
Postgres collates it as text.

The same bug had a second home. `ReleaseRef.ingested_titles` is built with
`tuple(sorted(...))` over the same unpadded numbers, and it renders on
`/app/releases` as "titles held".

A third list looked identical but is not affected: `titles_affected` holds
OLRC's *file-naming* form (`05`, `18a`), which is zero-padded and therefore
sorts correctly as a string below title 100 — and arrives in the inventory's own
order anyway.

## Decision

**1. Sort through an explicit key, in Python, not in SQL.**

```python
def title_sort_key(num: str) -> tuple[int, str]:
    """'16' → (16, ''), '5a' → (5, 'a')."""
```

Applied in `list_titles` and to `ingested_titles`. Fifty-eight rows is not a
sort worth pushing into Postgres in order to get it wrong; an expression index
or a `regexp_replace(...)::int` cast would buy nothing here and would put the
rule somewhere a reader of the protocol cannot see it.

An appendix title sorts directly *after* its parent — `5, 5a, 6` — because that
is where the Code puts it, not at the end of the list.

An unparseable number sorts last instead of raising. Rendering a list is not the
place to discover that ingest wrote something strange; the page still renders,
with the oddity visible at the bottom.

**2. The ordering is part of the `Repository` contract, not the caller's
problem.** `Repository.list_titles` now documents the guarantee. This is the
point of the ADR: XCiteDB becomes a second implementation of that protocol
(architecture rule 1), and a contract that lives only in the Postgres file is a
bug the port will faithfully reproduce. The frontend does no sorting of its own
and should not start — `frontend/src/pages/index.astro` passes the API's order
straight through, which is why one server-side fix corrects both `/app/` and
`/app/releases`.

**3. Do not reuse `_padded()`.** It exists to match `titles_affected` and
produces `05`/`18a`. Using it for ordering would still be a string comparison —
one that merely happens to work while the Code has fewer than 100 titles — and
it would change the `t{num}` identifier the front page builds hrefs from.

## Consequences

- `/api/v1/titles` returns `1, 2, 3, 4, 5, 5a, 6, 7, 8, 9, 10, 11, 11a, 12, …
  50, 50a, 51, 52, 54` — verified against the loaded 58-title corpus.
- Two test layers, deliberately not sharing code. `tests/test_title_order.py`
  checks the pure function with no database, including a test asserting that the
  string order it replaces really was different — a test that proves nothing if
  the two ever agree. `tests/test_api.py` checks the HTTP contract with its
  *own* comparator spelled out locally, because a contract test that imports the
  implementation's comparator passes whenever the two share a bug.
- Recorded as gotcha 16 in `CLAUDE.md`, because the shape of this mistake
  (string column, numeric meaning) will recur the moment someone sorts section
  numbers — `45f`, `2000e-2`, `78j-1` are the same problem, harder.

## Alternatives considered

- **An integer column plus a suffix column.** Correct in the abstract, but it
  splits an identifier that the source publishes as one token, and every
  `t{num}` href would have to reassemble it. Rejected: the identifier is the
  thing this project is organised around (ADR-0003).
- **A generated `sort_key` column with an index.** Worth doing at a scale this
  table will never reach.
- **Sorting in the frontend.** Puts the rule in the surface furthest from the
  data, and leaves the API wrong for every other client.

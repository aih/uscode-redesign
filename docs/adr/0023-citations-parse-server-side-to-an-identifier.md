# ADR-0023 — A typed citation parses server-side to an identifier

- **Status:** Accepted
- **Date:** 2026-07-29
- **Context:** Session 10 (UI refresh before deploy), BUILDLOG 024

## Context

PLAN §Day-2 has owed a "citation-style search box (`16 USC 45f(c)(5)` →
identifier)" since the first day. Until now the only ways into a provision were
walking down the hierarchy or already knowing that the URL scheme mirrors OLRC's
`@identifier`. Both require knowing the answer before asking the question.

This site has no full-text search and no search index, and does not need one for
this: a citation is a *structured* string, and turning it into an identifier is
parsing, not searching.

## Decision

**1. A pure parser, in its own top-level module.** `citeparse.py` — named for
distance from `citation.py`, the ADR-0010 redirector, because two modules a
letter apart is a trap. It imports no `storage`, no `db`, no `fastapi`, no
`sqlalchemy`, and `tests/test_architecture.py` fails if that changes.

Purity is the load-bearing part. It is what lets the whole accepted-forms table
— 84 cases in `tests/test_citeparse.py` — run in the default `make test` with no
database, no fixtures and no HTTP. The moment the parser imports `storage` "just
to check", that table needs a loaded corpus and stops being run.

**2. Existence is the API's question, answered with what already exists.**
`GET /api/v1/citation?q=` parses, then asks `Repository.labels()` — the batched
lookup built for citation hover text — whether the target is there. No new
`Repository` method; architecture rule 1 holds.

**3. Three different failures, three different answers.**

| Case | Response |
|---|---|
| Not a citation (`"garbage"`, `"523"` with no title) | **422** — a malformed request, with the accepted forms in the detail |
| A citation naming nothing loaded (`99 usc 1`) | **200, `exists: false`** — a well-formed question whose answer is "not here" |
| A citation this site structurally cannot resolve | 200, `exists: false`, plus a specific `message` |

A bare section number is refused rather than guessed. `523` names a section of
*some* title, and picking one would be a guess presented as an answer.

**4. The reader's box is a plain GET form.** No JavaScript, following
`ReleasePicker`. It lands on `/app/goto?q=…`, which 307s on a hit and otherwise
renders which of the three failures occurred. An autocomplete would need a search
index; a box that parses what you already know how to write needs only the
parser. An e2e test runs it with `javaScriptEnabled: false`.

## Rules, and where they came from

Ported from the three sources named in the plan:

- **`loadusc-xcitedb/loadusc/constants.py`** `USC_CITE_REGEX`, this project's own
  ancestor and the one the sibling `versions` service uses. Too narrow to adopt:
  its subsection class is `[a-z0-9]`, so `(B)` does not match; it knows no `§`,
  no `App.` and no inverted form. Its `#TODO handle plain text citations` is the
  gap this closes.
- **`versions/services_py/index.py`**, for how that regex was actually used.
- **[`unitedstates/citation`](https://github.com/unitedstates/citation)**,
  `citations/usc.js` — the fullest published ruleset, and the source of the three
  shapes handled here (standard; `section X of title Y`; `Section X, Y U.S.C.`)
  plus `App.`, `note` and `et seq.`. The rules are ported; the output is not —
  theirs is a JSON citation object, ours is a USLM identifier.

Two rules that will be got wrong if not written down:

- **Subdivision case is preserved.** `(B)` → `/B`, never `/b`. USLM identifiers
  are case-sensitive; `/us/usc/t16/s45f/c/5` is the fixture this project checks
  itself against.
- **`N app.` → `tNa`**, matching how the five appendix titles are stored.

## The two things found by typing citations at it

Neither was visible from the schema, and both are now tested.

**Dashes.** OLRC writes section numbers with an **EN DASH** —
`/us/usc/t16/s45a–1`, U+2013. Counted over the loaded corpus: **5,697 of 65,938
sections contain one, and not a single section contains a plain hyphen.** No
keyboard has that key, so `42 USC 2000e-2` — the way the citation is written
everywhere — matched nothing.

The parse keeps the dash the reader typed and carries `section_variants` (typed
first, then en dash, then em dash). The caller looks all of them up in the one
batched `labels()` call and takes the first that exists, so trying three costs
what trying one did. Generating candidates rather than rewriting is what keeps
the parser honest: `-` and `–` are different characters, and this layer does not
know which the corpus holds.

The knock-on: a raw en dash in a `Location:` header **throws** — a header value
is a ByteString — so both redirects in the app 500'd on those sections,
including the pre-existing `?id=` guid lookup. `lib/url.ts` now encodes every
href it builds.

**Appendix citations parse and cannot resolve.** `5 U.S.C. App. 3` names
`/us/usc/t5a/s3`, and OLRC publishes nothing there: **0 of 461 appendix sections
use the flat form**. They are `/us/usc/t5a/pl/92/463/s1` (public law) or
`/us/usc/t50a/act/1917-05-18/ch15/s212` (act by date). Rather than invent a
citation-to-public-law mapping, the parse carries `appendix=True` and the API
says plainly what happened — a bare "not found" would read as a bug in the
parser rather than a gap in what this site can address.

## Consequences

- Every reader href now percent-encodes, which is a behaviour change for the
  ~8.6% of sections whose identifiers are not ASCII.
- Structural nodes and titles are looked up with `get_toc`, not `labels()` —
  `11 USC ch. 5` and `title 11` reported `exists: false` while sitting in the
  database until that was split out.
- Appendix titles remain unreachable by citation. Recorded as an open debt, not
  as a defect: closing it needs a lookup table this project does not have.

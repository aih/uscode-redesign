# ADR-0068 — A table scope on the classification lookup

**Status:** accepted (2026-08-14)

**Task:** classification tables — finding one row in a session table without paging.

**Amends:** ADR-0067 (the lookup and the session pages it decided).

## Context

A session table page has four filters (`pl`, `pl_section`, `title`, `section`), rendered as
dismissible pills — and nothing on the page that sets one. A filter arrives from a lookup
suggestion on the index page or from a hand-edited URL. On the page itself, finding one row means
the pager: the 104th's table is 11,737 rows at 100 a page, 118 clicks of *Next*.

The lookup box existed only on `/app/classification`, so the reader standing on a table had to
leave it to search it. And the suggest endpoint had no notion of where the reader was standing: a
bare law number (`35`) or a provision (`35 101`) parsed to nothing, requiring the congress to be
retyped when the page's URL already names it.

## Decision

### 1. The suggest endpoint takes a table scope

`/api/v1/classifications/suggest` gains optional `congress` and `session` parameters — one without
the other, or a pair naming no held table, scopes nothing, and the corpus-wide answers are
unchanged either way. With a scope:

- **A bare law number means a law of the scoped congress.** `_PL_SHORTHAND_BARE` is the existing
  shorthand with the congress removed, and it is tried **only when `citeparse` read nothing in the
  query** — otherwise `16 usc 3831` becomes "Public Law 118-16 § usc 3831". The full form still
  names its own congress: `110-85` typed on the 118th's page is the 110th's law.
- **A citation gains a first suggestion counting that section's rows in the scoped table** (kind
  `section-in-table`, counted by `entries_for_file`), ahead of the corpus-wide two. A section with
  no rows in that table simply lacks the suggestion; the others still answer.

### 2. The session page carries the lookup, scoped to itself

`ClassificationLookup` takes a `scope` prop: the form posts back to the session page, `?q=` is the
no-script path (answered server-side by the same endpoint, rendered by the new
`ClassificationMatches` component both pages now share), and the suggest request carries the
scope. Choosing a match applies a filter — the table stays a page; what changes is that the page
can now be asked for a row.

### 3. The index lookup offers the scope as a `<select>`

`scopeOptions` renders a `<select name="scope">` of every held table, "Every table" first. The
value is `118-2` / `104-all` (`classificationScopeValue`), split at its **last** dash because the
session half is `1`, `2` or `all` and never carries one; `parseClassificationScope` reads it back
from the no-script `?scope=`, and a value naming no table scopes nothing rather than erroring. The
island appends the scope to the fetch and re-asks when the select changes.

## Consequences

- Finding a known row in a table is one query in place of up to 118 page turns.
- A fourth suggestion kind exists; `classificationSuggestionHref` builds its URL from the
  structured pieces like the other three, asserted against `_app_path`'s output in `url.test.ts`.
- The session pages ship the lookup island they did not carry: `docs/js-budgets.json` raises
  `/app/classification/[congress]` 18,500 → 24,000, `/app/classification` 23,000 → 24,000 (the
  island grew 534 bytes of scope handling), `/app/design` 39,000 → 39,500.
- `/app/design` renders both variants of the box — the select and the fixed scope — the scoped
  specimen under congress 0, which OLRC does not publish (ADR-0053's convention).
- The scoped suggest still runs on the person-sized rate budget (`classification_suggest`,
  30/5 s), and the in-table count adds one indexed query to a scoped citation lookup.

## What was declined

- **A field-per-filter form on the session page.** The four filters stay URL-and-pill; the lookup
  reaches the same filtered views through one box, and two entry mechanisms for the same filters
  is chrome the page does not need. Revisit if `pl_section`-prefix filtering turns out to be
  reached for on its own.
- **Restricting the full `NNN-NN` form to the scoped congress.** A law of another congress typed
  on a table page still leads to its own table.

## Addendum, 2026-08-14 — the empty scope, and the redirect that left the site

A `<select>` always posts its value, so a no-script submission with "Every table" chosen arrives as
`?scope=&q=118-42`. `/app/classification` answers it correctly and the URL is one nobody would
write, so the page redirects `scope=` away when it is present and empty.

The target is a path, composed from `classificationHref()` and the surviving parameters. Built as
`new URL(Astro.url)` with the parameter deleted, the redirect was
`http://localhost/app/classification?q=118-42` — port 80, off the site. Astro's Node adapter reads
`x-forwarded-host` and `x-forwarded-port` only when `security.allowedDomains` names the host
(`astro/dist/core/app/validate-headers.js`); with that unset it discards the request's own `Host`
as well and falls back to the literal `localhost` with no port, so `Astro.url.origin` is
`http://localhost` for every request behind `deploy/Caddyfile`. On the deployed box the same
redirect would have downgraded `https` to `http`. This was the only place in `frontend/src` that
built a URL from `Astro.url`; `classification.spec.ts`'s no-script test now asserts that the URL it
lands on carries no `scope`.

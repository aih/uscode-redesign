# ADR-0099 — A 404 for an address with no page

**Status:** accepted (2026-11-09)

**Amends:** ADR-0065 (the dead end), for addresses that are not citations.

**Related:** reintroductions-us `reintro/web/notfound.py`, the model this follows.

## Context

ADR-0065 gave a failed *citation* a way back: the nearest identifier above it, and when the
provision exists at other release points. An address under `/app` that no route serves — `/app/abuot`,
`/app/usc/t16/s45f`, `/app/About` — rendered `pages/404.astro`, which said "There is no page here" and
offered the front page. An address outside `/app` and `/api` reached FastAPI, which answered a browser
with `{"detail": "Not Found"}`.

reintroductions-us answers the same situation with a page that names the path, redirects a
letter-case variant of a page it serves, offers near misses ("Did you mean"), its search forms and the
sections of the site.

## Decision

1. **The 404 names the address** it was asked for.
2. **A letter-case or trailing-slash variant of a page is a 301 to the page.** `lib/notfound.ts`
   holds `STATIC_PAGES`, every route under `src/pages` without a parameter; `tests/notfound.test.ts`
   walks that directory and fails when a route is missing from the list.
3. **Did you mean** lists up to three addresses: the address read as a citation when one segment is
   a title (`t16`, `t5a`), then the pages whose path after `/app/` is within a similarity of 0.8
   (Levenshtein over the two lengths, difflib's default cutoff in reintroductions-us).
4. **Look up** links the address's words to `/app/goto`, the search box's own target, which redirects
   a citation and searches anything else. It is a link rather than a second search box: ADR-0065's
   reason stands, there is one box and it is in the chrome at every width. It is left out when the
   address reads as a citation, since the first suggestion already is that.
5. **Pages on this site** lists `SITE_SECTIONS`.
6. **A browser's 404 outside `/app` and `/api` is a 302 to the same path under `/app`**, query string
   kept, `Vary: Accept`. FastAPI's handler now catches Starlette's `HTTPException`, which is what an
   unmatched route raises. Only GET and HEAD whose `Accept:` prefers HTML (`negotiated_format`) are
   redirected; every other caller, and every `/api/` path, keeps the JSON body. `/app` itself is
   excluded so that `make dev` without the proxy does not loop.

## Consequences

- `STATIC_PAGES` is a second list of routes beside the filesystem; the ratchet test is what keeps
  them equal.
- The near-miss match is over page paths only. A misspelt section number under `/app/us/usc/…` is
  ADR-0065's case, served by the catch-all route, and is unchanged.
- An address outside `/app` costs a browser one extra redirect before the reader's 404.

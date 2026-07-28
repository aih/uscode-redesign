# ADR-0010: Reader and API separated; the citation URL becomes a thin redirector

**Date:** 2026-07-28 · **Status:** Accepted · **Amends:** ADR-0009

## Decision

The reader and the API get separate mounts, at Ari's direction, for robustness:

- **`/app/us/usc/…`** — the reader. Always HTML. Owns templates, static files, and the
  HTML error pages. Same identifier path scheme, same query params (`?release`, `?date`).
- **`/api/v1/us/usc/…`** — the API. Always machine formats (JSON default, `?format=xml`
  for verbatim USLM). No Jinja import anywhere under `api/`.
- **`/us/usc/…`** — the **citation URL**, kept alive as a thin negotiating redirector:
  browsers (HTML wins q-value negotiation) get **307 → `/app/us/usc/…`** with the query
  string preserved; machine clients get **307 → `/api/v1/us/usc/…`**. `Vary: Accept`,
  cacheable. `?format=` still wins over the header, exactly as before.

## Rationale

ADR-0009's principle — a citation is one URL — survives; its *mechanism* (one handler
serving two representations) is what changes. Serving both from one route meant the API
carried a template engine, HTML error handlers, and `Accept:` parsing in its request
path, and the two surfaces could not be cached, rate-limited, deployed, or swapped
independently. Separation buys: pure-JSON `api/` (the Session-5 negotiation bug class
disappears from it), independent CDN rules (long-cache immutable HTML under `/app`,
API caching by ETag), the option to scale or replace the frontend (SPA, static export)
without touching the API, and cleaner OpenAPI docs that describe only machine routes.

The bare URL had to stay: it is what people paste, cite in briefs, and print. A 307 is
one round-trip and preserves method + query; the redirector holds no logic beyond
q-value parsing, which moves out of `api/deps.py` into the small root router.

## Alternative rejected

A hard split (bare `/us/usc/…` serving the API only, reader reachable only at `/app`)
was rejected: pasting a cited URL into a browser would dump raw JSON on a reader —
wrong default for a citation-first site.

## Consequences

- `web/` gains its own router mounted at `/app`; `api/routes.py` loses the HTML branch
  and the delegation to `web/reader.py`; a small root module owns `/us/usc/…` redirects.
- Every link the reader emits (breadcrumbs, TOC, prev/next, picker, refs) must target
  `/app/…` — one helper, not string concatenation at call sites. Ref hover-text work
  (Session 7) builds on that helper.
- The `/` home page moves conceptually under the reader; `/` itself redirects or serves it.
- Tests: negotiation tests become redirect tests on the bare URL; reader tests hit
  `/app/…`; a new architecture test asserts `api/` imports no Jinja and `web/` no longer
  reaches into `api/` internals.
- README/demo commands change meaning slightly: `curl` on a citation URL now follows a
  redirect (`curl -L`), or hits `/api/v1/…` directly. Update README when this lands.

# ADR-0015: One origin, two services; the USLM renderer lives in the frontend

**Date:** 2026-07-28 · **Status:** Accepted · **Implements:** ADR-0010, ADR-0011

Two decisions Session 7 had to make that ADR-0010 and ADR-0011 deliberately left open:
how the two surfaces share an address, and where USLM becomes HTML.

## Decision 1 — a proxy owns the port; the services never see each other

```
browser :8000 ── Caddy ─┬── /app/*  → frontend:4321   (Astro 5 SSR on Node)
                        └── /*      → api:8001        (FastAPI: /api/v1, /us/usc, /docs)
```

`deploy/Caddyfile` is checked in; `docker compose up --build` (`make dev-all`) is the whole
site. `make dev` runs the API alone and `make dev-web` the reader alone — and those now mean
different things, which the Makefile says out loud.

**Why a proxy and not the alternatives.** The citation URL 307s to `/app` or `/api/v1`
(ADR-0010), and a redirect that crossed origins would break `Accept:`-based routing and
anything a browser scopes to a host — so *something* has to put both surfaces on one origin.
Making FastAPI reverse-proxy `/app` to Node was the tempting shortcut: no new service, one
port everywhere. It was rejected because it re-couples exactly what ADR-0010 separated —
every reader page would traverse the Python process, and the two could no longer be scaled,
cached, or rolled back apart. Making Astro the front door was rejected for the same reason
in the other direction: the API's availability would depend on the frontend's.

Caddy costs one container and buys the independence the split was for.

## Decision 2 — USLM → HTML is rendered in the frontend, not by the API

`web/uslm_html.py` is ported to TypeScript at `frontend/src/lib/uslm.ts`. The alternative
ADR-0011 left open — a `html` field on `SectionOut` — was rejected.

**Why.** CLAUDE.md architecture rule 5 already named the answer: presentation is *the sole
place outside the parsers allowed to know USLM element names*, and it lives in the renderer
"and its typed successor in the Astro app". A rendered-HTML field would put element names,
class mappings, and anchor decisions back inside `api/` — the layer whose freedom from
frontend concerns is what makes it swappable for XCiteDB and makes the frontend swappable
for anything else. `SectionOut.xml` already ships the verbatim fragment, so the frontend
needs no extra call to do the work itself.

The port is element-for-element (`@xmldom/xmldom`, the same tag map, `@class`/`@style`
copied through, `@identifier` → `id`, `<div>` fallback for unknown elements), plus the two
things the Python renderer could not do: references resolved rather than copied, and hover
text from labels the page fetched in one batch.

**Consequence, stated because it is a real cost:** `make test` no longer covers reader
rendering. That coverage is `make test-web` (Vitest over the renderer and the reference
rules) plus the screenshot run, and CI must run both. The Python suite dropped from 244 to
209 tests when the Jinja reader retired; 27 frontend tests replace them.

## Decision 3 — references link to something that exists, or do not link

Consequence of the BUILDLOG 008 bug, encoded in `frontend/src/lib/refs.ts` and **verified
against govinfo before being written down**:

| Reference | Becomes | Verified |
|---|---|---|
| `/us/usc/…` | `/app/us/usc/…?release=` + `title=` hover text | — |
| `/us/stat/{vol}/{page}` | `https://www.govinfo.gov/link/statute/{vol}/{page}` | `123/1764` → 302 to STATUTE-123 Pg1734 `#page=31` |
| `/us/pl/{congress}/{num}` where congress ≥ 104 | `https://www.govinfo.gov/link/plaw/{congress}/public/{num}` | `104/1` → 302; `103/1` → **400** |
| `/us/pl/…` below the 104th, `/us/act/…`, anything else | plain text, no link | govinfo's PLAW collection starts at the 104th |

A citation that 404s is worse than a citation that is not a link, because it looks like the
site lost the law. Older public laws are usually reachable anyway through the `/us/stat/`
reference beside them in the same source credit.

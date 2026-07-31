# ADR-0032: The interactive API docs are served from this origin

**Status:** Accepted
**Date:** 2026-07-31
**Extends:** [ADR-0030](0030-browser-security-headers.md) (the CSP this had to be reconciled with)

## Context

`/docs` and `/redoc` had been mounted since Session 3 and neither had rendered since Session 13.

Both answered **HTTP 200 with a complete, correct HTML body**. Nothing was in the server logs,
`curl` showed exactly the markup FastAPI is supposed to emit, and both routes were covered by
smoke tests that asserted a 200. What a browser showed was an empty page.

The cause is one line of `deploy/Caddyfile`:

```
default-src 'self'; … script-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'
```

FastAPI's stock docs pages load their JavaScript from `cdn.jsdelivr.net`, their favicon from
`fastapi.tiangolo.com`, and — in ReDoc's case — two typefaces from `fonts.googleapis.com`. Six
external requests across the two pages, every one of them blocked. ADR-0030 wrote that policy as
*a description of a site that loads no third-party anything*, which was true of the reader and
had never been true of these two pages.

This is worth dwelling on as a class of bug rather than as an incident. Every signal available on
the server said the pages were fine; the only place the failure existed was in a browser console
nobody had opened. A test asserting `200` is not a test that a page works.

## Decision

**Vendor Swagger UI and ReDoc into `static/apidocs/` and serve them from this origin.**

- `docs_url=None`/`redoc_url=None`, and `main.py` mounts its own two routes through
  `get_swagger_ui_html` / `get_redoc_html` with same-origin asset URLs,
  `with_google_fonts=False`, and this site's own favicon.
- `scripts/vendor_apidocs.py` fetches pinned versions and records a URL and a sha256 per file in
  `static/apidocs/MANIFEST.json`. `--check` recomputes them and `tests/test_apidocs.py` runs it,
  so an edited-in-place or half-downloaded bundle fails the suite.
- `tests/test_apidocs.py` asserts what the CSP would otherwise assert silently in a browser:
  **no `src` or `href` in either page names another origin**, and every same-origin asset each
  page names actually answers 200.

**One directive is added to the CSP: `worker-src 'self' blob:`.**

ReDoc builds its search index in a worker created from a `Blob`. With no `worker-src`, the
browser falls back to `script-src`, which has no `blob:` — so `/redoc` rendered in full and its
search box returned zero results for every query, measured. Naming the directive is what keeps
the widening narrow: it permits a worker to be created from a blob and changes nothing about what
may execute *in the page*, which is what `script-src` governs and which is unchanged.

**The site's favicon moves here too.** `static/favicon.svg`, served at `/favicon.svg` by the API,
linked root-absolute from `Base.astro` and from both docs pages. One file for the whole site,
because `/favicon.svg` is not under `/app` and Caddy sends everything that is not to this process.

## Alternatives rejected

**Add `cdn.jsdelivr.net` to `script-src`.** One line, and permanently puts a third-party script
origin into the policy that sits under the reader's `set:html` sinks — where statutory XML is
rendered to HTML — in order to serve two developer pages. The reader is the thing being
protected; the docs are the thing being fixed.

**Delete `/docs` and `/redoc` and keep only `/app/docs`.** Tempting, because Session 14 already
built a readable API reference inside the site precisely because these pages were a different
site with no way back. But `/app/docs` is server-rendered prose with no *Try it* button, and
losing the ability to send a request from the documentation is a real subtraction — it is the
one thing Swagger UI is for.

**Download the bundles at image build time instead of committing them.** Keeps ~2.4 MB out of
git, and makes the build require the network and a third party's uptime — including CI, and
including `make dev` on a laptop with no connection. The manifest is what makes committing them
defensible: anyone can say what the bytes are and re-derive them.

## Consequences

- **2.4 MB of minified third-party JavaScript is in the repository.** Checkable by sha256, pinned
  by version, and upgraded deliberately (`--update` after a version bump).
- Upgrading Swagger UI or ReDoc is now a commit here rather than a silent CDN roll. That is a
  cost — a security fix in either does not arrive on its own — and it is the same cost the
  no-CDN decision already accepted everywhere else on the site.
- `main.py` serves a `static/` directory, which its docstring previously said it did not. Amended
  there rather than left to be discovered.
- ReDoc still tries to load its own Redocly logo from `cdn.redoc.ly`, which stays blocked and
  degrades to the text "API docs by Redocly". Not worth a CSP entry.
- `HEAD` is still 405 on `/api/v1` routes (an existing debt); the two docs routes are GET-only
  for the same reason and inherit it.

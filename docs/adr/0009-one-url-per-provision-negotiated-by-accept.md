# ADR-0009: One URL per provision, with `Accept:` choosing reader or API

**Status:** Accepted — 2026-07-28 (Session 5)
**Context:** PLAN.md §4 (content negotiation), §5 item 5 (the reader), §10 (demo definition
of done); ADR-0003 (identifier semantics).

## Context

The reader needed addresses. Three shapes were available:

1. **A separate prefix** — `/read/us/usc/t16/s45f` for people, `/us/usc/t16/s45f` for
   programs.
2. **A separate app** — a React client against the JSON API, served from `/`.
3. **The same URL for both**, with `?format=` and `Accept:` deciding the representation.

PLAN §1 makes the whole project's claim "a citation is a URL and a URL is a citation". A
second prefix breaks that immediately: `16 USC 45f(c)(5)` would have two web addresses, one
of which is the one people paste into briefs and the other of which is the one that
survives in `curl`. Anything built on the identifier later — watchlists (Day 5), the guid
citation form, the version timeline — would have to pick a side and would pick wrongly for
half its callers.

## Decision

**`/us/usc/…` is one route, serving whichever representation the caller asked for.**
`?format=html|xml|json` is explicit and wins; otherwise `Accept:` decides. `api/routes.py`
negotiates and delegates the HTML case to `web/reader.py`; `/api/v1/…` remains
machine-only, and the front page (`/`) is the reader's own route.

The reader is **server-rendered Jinja with one stylesheet and no build step**. The pages are
documents; the only JavaScript in the whole reader scrolls a highlighted provision into
view, and every other behaviour — including the release picker, which is a GET form —
works with scripting off. That also keeps `web/` on the `Repository` interface (rule 1)
rather than on a second, JSON-shaped copy of it: the reader calls the same methods the API
does, so the XCiteDB swap moves both at once.

## Consequences

- `api/render.py` moved to `web/uslm_html.py`: presentation is now one layer, and the
  architecture test's "the renderer is the one place outside the parsers that may know
  element names" exception moved with it.
- **Negotiation had to become real.** The Session 4 implementation tested
  `"application/xml" in accept`, which matches the header Chrome actually sends
  (`text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8`) — so every browser
  visiting the PLAN §10 demo URL got raw USLM, and `?format=html` was covering for it in
  every test we had. `negotiated_format` now reads q-values, highest wins, ties to the
  client's own order, unknown media types fall back to JSON. Found by screenshotting the
  demo URL in a headless browser rather than by a test, which is the lesson: a header
  written by hand in a test is not the header a browser sends.
- One URL means one cache entry. The ETag is the content hash (PLAN Day 6), which is the
  same for the HTML and the JSON of a provision, so identifier responses now send
  `Vary: Accept` — without it the first caller's representation would be handed to the
  next caller of the other kind as soon as a CDN goes in front (Day 6).
- A 404 or a 409 now answers in the negotiated format too, because a reader that hands a
  person a JSON blob has stopped being a reader exactly when it most needs to explain
  itself.

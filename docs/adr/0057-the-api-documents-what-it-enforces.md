# ADR-0057: The API documents what it enforces, including the routes the reader does not use

**Status:** Accepted (2026-08-06)

**Context:** ADR-0029 (request identity and rate limits); ADR-0032 (serve the API docs assets
ourselves); ADR-0034 (features built and switched off say so); ADR-0038 (the user guide is
executable); `claude-code/DOC-AUDIT-TASKS.md` Tier 4.

The 2026-08-06 documentation audit read the OpenAPI surface — `/docs`, `/redoc` and the `/app/docs`
page that renders the same document — against the code that serves it, and found four gaps.

1. **The rate limits appeared nowhere in the document.** Five routes are throttled and answer 429
   with `Retry-After`; `main.py`'s app description did not mention throttling, and the only
   statement of it anywhere was one sentence of guide chapter 08 giving no numbers.
2. **429 was declared on three routes and returned by five.** `/citation`, `/labels` and `/diff`
   declared it. `/api/v1/search`, `POST /auth/login` and `POST /auth/signup` returned it
   undeclared, so a generated client had no case for it.
3. **Fifteen routes had no summary and no description** — all four under `/api/v1/auth`, eight of
   the nine watchlist routes, one of the two settings routes, and `/health`. In Swagger UI those
   render as a bare method and path.
4. **`/api/v1/labels` enforces a bound of 100 identifiers and never stated it**, so a caller learnt
   it from a 422.

Behind (3) sat an open question the audit declined to settle: whether the guide should name the
auth, watchlist and settings routes at all. Accounts are switched off in the reader (ADR-0034), and
the argument for silence is that documenting a route invites its use.

**Decision:**

1. **The OpenAPI document states every limit it enforces.** The app description carries the rate
   limit table — route, burst capacity, sustained rate — the login throttle's failure counts, and
   the fact that `HEAD` answers 405 on every route. Guide chapter 08 carries the same table, in the
   same units.
2. **Every route declares every status it can return**, and every route carries a summary and a
   description.
3. **Guide chapter 08 names the accounts, watchlist and settings routes**, in one sentence, saying
   that accounts are switched off in the *reader* and that the routes answer a direct caller.

**Consequences:**

Decision 3 is ADR-0034 applied to the API surface. The routes are already in the OpenAPI document
that `/docs`, `/redoc` and `/app/docs` all render, so the alternative was not silence but a guide
that described a smaller API than the one being served — the failure mode ADR-0038 exists to catch.
CLAUDE.md already records `POST /api/v1/auth/signup` as working for a direct caller; the guide now
says the same thing to the reader of the guide.

The app description is written to the markdown subset `/app/docs` renders — paragraphs, bullets,
code spans, bold and italic (`frontend/src/lib/openapi.ts`, `renderMarkdown`). It supports neither
headings nor pipe tables, so the limits are a bullet list rather than the table guide 08 prints; a
table in the description would arrive at `/app/docs` as one run-on paragraph while rendering
correctly at `/docs` and `/redoc`.

The rate limit numbers are now written in three places: `params.rate_limit` calls, the app
description, and guide 08. Nothing checks that the three agree. A limit changed in the code and not
in the prose is a documentation defect the guide ratchet cannot see, because the ratchet checks
that a route is *covered*, not that a number is *right*. Deriving the table from `params.LIMITERS`
at render time would close it and is not done here.

Declaring a status code does not implement it. `429` on `/api/v1/search` was returned before this
ADR and is returned after; what changed is that a client generated from the document now has a case
for it.

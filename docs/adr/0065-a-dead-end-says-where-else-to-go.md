# ADR-0065 — A dead end says where else to go

**Status:** accepted (2026-08-11)

**Task:** workstream B, B6 — dead ends and disappearances.

**Amends:** ADR-0029 (the rate limiter now has a page), and extends the 404 behaviour ADR-0010 left.

## Context

Three shapes of dead end, none of them handled well.

**A 404 offered one way out, and it was the front page.** `ErrorPage` said which release point it had
searched — which is the fact that separates "no such provision" from "not at this release point" —
and then "Start from the top". On a site whose whole address scheme is a hierarchy, the thing the
reader wanted is almost always one level up from the thing they typed.

**An identifier can vanish at a release point without being repealed** (gotcha 3). The 404 for that
is word for word the 404 for a typo, so the reader cannot tell a provision that has not been enacted
yet from one they have misspelled.

**Appendix titles are unreachable by citation and only one surface said so.** `5 U.S.C. App. 3`
parses to `/us/usc/t5a/s3`; OLRC publishes nothing there — 0 of the corpus's 461 appendix sections
use the flat form, they are `/us/usc/t5a/pl/92/463/s1` or `/us/usc/t50a/act/1917-05-18/ch15/s212`.
`/api/v1/citation` explained this in its `message`; `/api/v1/us/usc/t5a/s3` and therefore the whole
reader answered a bare "nothing at …".

**A shed request was not a page at all.** `/app/diff/` is rate limited (ADR-0029) and is a page a
reader navigates to, not a fetch. Over the limit, `middleware.ts` returned `text/plain` — no chrome,
no navigation, no way back, and no sign the site had not simply broken.

## Decision

### 1. The nearest identifier above the failed one, with the trail to it

`ancestorIdentifiers()` walks the identifier from nearest to furthest and stops at the title:
`/us/usc/t16/s45f/c/5` → `/us/usc/t16/s45f` → `/us/usc/t16`. `nearestAncestor()` tries them in order
and returns the first that resolves, with that node's own ancestors. A mistyped subsection of a real
section offers the section; a section that is not there offers the title.

Every call inside it is allowed to fail and is swallowed. This runs on a page that is already an
error, and a second error while explaining the first should cost the reader nothing. When nothing
above resolves either, nothing is offered — a made-up trail points at another 404.

It is rendered as a list in the page body, not through the `Breadcrumbs` component in the sticky
chrome. The chrome's trail says *where you are*; this one names somewhere the reader is not.

### 2. A 404 for a section that exists at other release points says when

`/versions` spans every release point, so it answers the question a 404 raises and the release point
in the message cannot: the provision is in the Code at N release points, from the first to the last,
and here is its version history. One extra call, on a page nobody reaches on purpose, in parallel
with the ancestor walk.

### 3. One appendix explanation, given by both surfaces

`_appendix_hint()` is written against the identifier rather than against a `ParsedCitation`, and both
`/api/v1/citation` and the identifier lookup call it. The identifier lookup appends it to the 404
detail, which the reader already renders — so the reader got this for free, and an API client and a
browser now get the same sentence. It names **both** real forms rather than one.

It matches the flat form alone (`/us/usc/tNa/s…`). A real appendix identifier that failed for some
other reason gets no message, because a confident invented reason is worse than "not found".

### 4. The rate limiter gets a page, at the URL that was refused

A request whose `Accept` includes `text/html` is rewritten to `/app/429`, which renders the error
page with the whole chrome; the middleware wraps the render to attach `Retry-After` and
`Cache-Control: no-store`. `context.rewrite` rather than a redirect, so the URL the reader asked for
is still in the address bar and reloading it is the retry.

A caller that did not ask for HTML — the hover card's fetch, which reads the status and says
"Preview unavailable" itself (ADR-0041) — still gets the plain-text body it was already handling.

The 429 page offers the identifier **itself**, not its parent: a shed request refused the *work*, and
the provision it was asked about is still there. That is the one place `nearestAncestor` is called
with `includeSelf`.

## Consequences

### What this costs

**A 404 now makes up to three API calls where it made none.** The ancestor walk is one call per
ancestor until one resolves — at most a handful, since a section identifier has few segments — plus
one to `/versions`. It is on the error path only, and `ErrorPage` swallows every failure, so the
worst case is the page the reader would have got anyway.

**`/app/429` is a route that exists and is in no guide chapter.** It is in
`UNDOCUMENTED_ROUTES` beside `/app/404`: neither is a route a reader types or ever sees in the
address bar, so what they do is documented where the thing that fails is documented — the rate limit
in chapter 04, the 404 in chapter 01.

**The 429 page costs every route 0 bytes and this branch one more budget line.** `/app/429` carries
`Base`'s inline scripts like any page; its ceiling is in `docs/js-budgets.json`.

**The redirects table gotcha 3 suggests is declined.** Building one needs a machine-readable map from
a vanished identifier to where its subject matter went, and OLRC publishes no such map — the
information is in the notes as prose, per section, in English. What is buildable without it is what
decision 2 does: report *when* the identifier existed, from data the corpus already holds, and let
the reader read the repeal or transfer note themselves. A redirects table populated by guessing would
send a reader to a provision that is not the one they wanted, silently, which is worse than the dead
end it replaces. Revisit when per-release structural history lands, which is already owed.

**No search box on the error page**, which is what B6 asked for. This site has exactly one search box
(ADR-0023) and since ADR-0064 it is in the chrome at every width, including on these pages. A second
would duplicate the `site-q` id that `/` and the shortcut map both reach by, and put two boxes on
screen with one of them filled in — the arrangement ADR-0061 removed. The error page points at it in
a sentence instead.

### What it buys

A 404 leads somewhere. A provision that is absent *here* says where in time it is present. The
appendix answer is one sentence written once and given by both surfaces. And the most expensive page
on the site sheds into a page rather than into a wall of plain text.

### Traps hit here

**`defineMiddleware` had a synchronous handler.** Adding `await context.rewrite(...)` failed the
build with `"await" can only be used inside an "async" function` — esbuild, at build time, not at
runtime, which is the good direction.

**A rewritten render carries its own status.** `new Response(rendered.body, rendered)` copies it, so
`/app/429` sets `Astro.response.status = 429` itself; without that the page renders correctly under
a `200` and the limiter silently stops being observable to any client that reads the status.

**The limiter cannot be exercised by navigating.** The diff bucket refills a token every two seconds
and rendering a diff takes about that long, so a loop of `page.goto` drains and refills at the same
rate and never reaches the limit. `deadend.spec.ts` spends the bucket through the request context —
same tokens, none of the rendering — and then navigates once.

**A trailing dash is a joiner, not punctuation.** USLM writes `Title 16—` as the number and
`CONSERVATION` as the heading, so joining them with a space gives `Title 16— CONSERVATION`.
`Breadcrumbs` strips the dash because it shows numbers alone; this trail shows both, so it closes the
gap instead.

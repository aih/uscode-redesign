# ADR-0030 — Browser security headers, and an honest CSP

- **Status:** Accepted
- **Date:** 2026-07-30
- **Context:** Session 13, cleanup phase 1 (S3, S6); `docs/cleanup-plan.md`

## Context

`deploy/Caddyfile` sent `Strict-Transport-Security`, `X-Content-Type-Options`
and `Referrer-Policy`, and nothing else. There was no `Content-Security-Policy`
and no framing protection anywhere in the repository, so:

- **The whole site was frameable.** A reader could be framed invisibly and
  clicked into a watchlist change or a logout.
- **The four `set:html` sinks in the reader had no backstop.** The renderer
  escapes every text node and attribute (`uslm.ts`), and the search page's
  snippet sink is not currently reachable — `strip_xml_tags` removes markup
  before indexing, so no raw `<` reaches the index. That is one ingest change
  away from being false, and defence in depth is the point of a CSP.

Separately, and in the same area of the site, `?next=` on both auth pages was
taken at face value: `login.astro` read it, carried it in `data-next`, and the
island passed it to `window.location.assign`. `signup.astro` was identical. So
`/app/login?next=https://evil.example/` was an **open redirect off the trusted
origin at the moment a password is being typed**, and `?next=javascript:…`
**executed in this page's own origin**.

## Decision

**1. `safeNext()` in `frontend/src/lib/url.ts`, an allowlist.** The value must be
a path on this origin beginning `/app/`; anything else falls back to
`provisionsHref()`. Control characters are stripped first, because browsers
ignore them when parsing a URL and a check that did not would read
`java\tscript:` as a path where `assign` reads it as a scheme.

An allowlist rather than a denylist, deliberately: `//evil`, `/\evil`,
`java\nscript:`, percent-encoded schemes and their combinations are an
open-ended set, while "starts with `/app/` and names no scheme or authority" is
checkable. Validation happens **server-side in the frontmatter**, so the only
value reaching the island is one this origin already agreed to navigate to.

Both pages also hardcoded `/app/provisions`, violating architecture rule 5 while
`provisionsHref()` sat unused with zero callers.

**2. Framing refused in both spellings.** `X-Frame-Options: DENY` for anything
predating CSP, `frame-ancestors 'none'` for everything else. Nothing on this
site has a reason to be framed.

**3. A CSP that describes what the site already does.**

```
default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none';
form-action 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self';
script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'
```

The site loads no third-party anything — no CDN, no web font, no analytics —
which is downstream of ADR-0011's no-bundle choice and ADR-0022's rejection of a
client framework. So `default-src 'self'` is not a restriction that had to be
negotiated; it is a description, which is what makes it safe to enforce.

**4. `includeSubDomains` on HSTS.** A real commitment rather than a free
upgrade: every subdomain of `$SITE_ADDRESS` must then be HTTPS for as long as
the max-age, including ones that do not exist yet. Accepted because ADR-0020
deploys a single host, and a plain-HTTP sibling of a site serving law is not
worth leaving room for.

**5. Headers set with Caddy's `?` prefix**, so an origin that wants to speak for
itself on a given route still can. None currently does.

## Consequences

**`script-src` carries `'unsafe-inline'`, and the policy is weaker than it
looks.** Saying so plainly is better than implying otherwise. Every island is
`<script is:inline>` — there are eight — which is ADR-0022's deliberate
no-framework choice, and the theme toggle in particular *must* run inline before
first paint or the page flashes light before going dark (ADR-0027). With
`'unsafe-inline'` present, an injected `<script>` would still execute; what the
policy stops is exfiltration to another origin (`connect-src`), `<base>`
hijacking, plugin content, framing, and form posts off-origin.

Nonces are the fix. They need per-request header generation, which means the
Astro middleware — and [ADR-0029](0029-request-identity-and-rate-limits.md) has
just added exactly that file. This is a follow-up with somewhere to go rather
than a wish, and it is in `docs/backlog.md`.

`style-src` is the same story for a smaller reason: USWDS ships bundled CSS, but
a handful of components still carry `style="…"` attributes.

**A CSP is only as good as its delivery.** These headers come from Caddy, so
`make dev-web` (Astro alone on :4321) does not send them. `make dev-all` is the
deployed shape and does.

## Verification

- `frontend/tests/url.test.ts` — `safeNext` against `//evil`, `/\evil`,
  `\\evil`, `https://evil`, `javascript:`, `java\tscript:`, `java\nscript:`,
  leading-space `javascript:`, `data:text/html`, `/api/v1/…`, `/appearances`,
  `/app`, null, undefined, empty — and that a real `/app/…` path with a query
  string survives intact.
- `caddy validate --config deploy/Caddyfile --adapter caddyfile` — valid.
- `curl -I` against `make dev-all` shows CSP, `X-Frame-Options`, and HSTS with
  `includeSubDomains`.

# ADR-0096 — API tokens for known callers

**Status:** accepted (2026-10-30)

**Builds on:** ADR-0029 (per-caller rate limits), ADR-0084 (the windowed versions route shares the
diff's budget), ADR-0088 (one budget for every outside caller on pinned routes).

## Context

reintroductions-us prepares a bill of one Congress for reintroduction in the next and checks every
US Code section the bill cites against this site: the section's timeline
(`/sections/{id}/versions`), its classification rows (`/classifications/code/{title}/{section}`),
and its current text. The 119th Congress's introduced bills carry 41,265 US Code citations. The
budgets that caller meets are per address and sized for a person: the windowed timeline is one
call every 5 seconds after a burst of 5, the classification routes 10 a second, and pinned lookups
share one budget of 6 a second with every other outside caller. A bill checked on request fits;
the same checks run ahead of time over a Congress do not, and a caller running them from a cloud
host shares its address with others.

## Decision

1. A token is sent as `Authorization: Bearer <token>`. `USC_API_TOKENS` holds, per named token,
   the SHA-256 digest of the token and a `scale`, as JSON. Only the digest is configured; the
   token is shown once, by `scripts/api_token.py`, to the caller.
2. A request carrying a configured token is keyed in every per-caller limiter as `token:<name>`
   rather than by address, and each budget it meets is multiplied by the token's `scale`
   (default 10): both the burst and the refill rate.
3. A token holder is exempt from the shared outside-world budget on pinned routes, as the
   reader's own server-side calls are.
4. A bearer token that matches no configured token is a `401` with `WWW-Authenticate: Bearer`,
   not the anonymous budget.
5. The token is read where a budget is applied. A route with no limiter ignores the header.
6. Revoking a token is removing its entry and restarting the API.

## Consequences

- The limits stay in the process (ADR-0029's recorded cost); a token's bucket is per process.
- A token raises a caller's budget and grants nothing else: no route, field or write is behind it.
- The token travels in a header on every request, so it is only as private as HTTPS keeps it.
- Nothing records per-token use beyond the proxy's log; a quota or usage report is not built.

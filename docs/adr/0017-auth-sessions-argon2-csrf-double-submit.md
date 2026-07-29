# ADR-0017: Server-side sessions (argon2 + sha256-hashed tokens), double-submit CSRF, and a second storage module for accounts

**Date:** 2026-07-28 · **Status:** Accepted · **Implements:** Day 5 (PLAN.md)

## Context

PLAN §4 calls for email+password auth and watchlists: `users`/`watchlists`/`watchlist_items`
have existed since Session 1 but nothing wrote to them. Three questions had to be answered
before writing any code: how a session is represented, how CSRF is enforced on the
state-changing routes the task calls for by name, and where the SQL for any of this lives
given CLAUDE.md architecture rule 1 ("No raw SQL in API handlers... `storage/postgres.py`,
the only SQL in the project").

## Decisions

**1. Sessions are server-side rows, not signed cookies.** `auth_sessions.id` is
`sha256(token)`; the cookie carries the raw `token`, which never touches the database. A
signed-cookie session (HMAC'd claims, no DB row) was the lighter alternative, but it makes
logout unable to revoke anything — the server would only ever tell the browser to forget a
token it would still accept from anyone else who had it. A revocable session is worth one
extra indexed lookup per authenticated request, and `auth_sessions` costs nothing this
schema didn't already pay for (`users`/`watchlists` are also plain rows).

**2. Passwords are argon2 (`argon2-cffi`), sessions expire after 14 days, and a login that
finds an outdated hash (`check_needs_rehash`) re-hashes on the spot.** Argon2id is the
current OWASP recommendation and the library's default variant; no parameters were tuned
beyond the library default, which is deliberately conservative rather than fast.

**3. CSRF is a double-submit cookie, checked only on routes that act on an existing
session — not on signup/login.** `usc_csrf` is a second cookie, generated alongside the
session token, `HttpOnly=false` so client-side JS can read it and set `X-CSRF-Token` on
mutating `fetch` calls; `require_csrf` compares the header to the session's own stored
value with `secrets.compare_digest`. This protects logout and every watchlist mutation,
where a forged cross-site request would ride an existing, valuable session.

Signup and login are deliberately exempt. There is no session yet for a forged request to
hijack, and two things happen to already block the more subtle "login CSRF" (a forged login
that logs the victim's browser into an *attacker's* account): both routes accept only
`application/json`, which a plain HTML `<form>` cannot send without JavaScript, and this
process runs with no CORS middleware, so a cross-origin `fetch` sending JSON triggers a
preflight `OPTIONS` that gets no `Access-Control-Allow-Origin` and never reaches the
handler. A same-origin page — the only kind that can call these routes with JSON at all —
is not a forgery. This is the same reasoning that makes the reader's login/signup pages
small `fetch`-driven islands (`frontend/src/components/WatchButton.astro`'s sibling forms)
rather than plain HTML forms: a plain form is exactly the attack surface JSON-only closes
off, and reopening it to get a no-JS login page back was judged not worth it for two forms
on a site whose reading surface is otherwise unscripted.

**4. Accounts get a second storage module, `storage/accounts.py` /
`storage/postgres_accounts.py`, rather than new methods on `Repository`.** `Repository`
(`storage/repository.py`) is specifically the version-resolution interface CLAUDE.md's
architecture rule 1 names — `resolve_release`, `get_section`, `get_toc`, and the like — and
its own contract test (`test_the_repository_protocol_and_the_postgres_implementation_agree`)
exists to keep it in lockstep with one Postgres implementation. Users, sessions, and
watchlists are ordinary CRUD with no release point in sight; bolting them onto `Repository`
would make that protocol answer two unrelated questions ("what does the law say" and "what
is this user watching") and would make a hypothetical XCiteDB `Repository` implementation
respons­ible for user accounts it has nothing to do with. A second, narrower protocol
(`AccountsRepository`) gets its own contract test
(`test_the_accounts_protocol_and_the_postgres_implementation_agree`) and its own Postgres
implementation, `PostgresAccounts` — a sibling of `PostgresRepository`, not a subclass or an
extension of it. Both still satisfy the actual rule that matters: `api/` holds no database
session and writes no SQL (`storage.get_accounts` is a FastAPI dependency exactly like
`storage.get_repository`), enforced the same way, by the same architecture tests, because
both modules live under `storage/`.

**5. Enrichment reuses `Repository.labels()` instead of a new query.** A watchlist item's
current `num`/`heading`/`status` — the mechanism behind "badge it if it went repealed since
being added" — is fetched by grouping items by their resolved release point and calling the
same batched `labels()` a section page already uses for its citation hover text
(`api/watchlists.py`'s `_enrich`). This is not new version-resolution logic in `api/`: it is
the existing `Repository` answering the same question it always answers ("what does this
identifier say at this release point"), just from a different caller.

## Consequences

- Logging out actually revokes the session (`DELETE FROM auth_sessions WHERE id = ...`) —
  the cookie alone is now provably useless the moment that happens, not just discouraged.
- A stolen `usc_csrf` value is useless without the matching `usc_session` cookie (which is
  `HttpOnly` and never readable from script), and a stolen `usc_session` value used from a
  different origin still can't drive a mutating request without also knowing `usc_csrf` —
  the two cookies are a matched pair, not two independent secrets.
- Two Postgres-backed modules under `storage/` (`postgres.py`, `postgres_accounts.py`) means
  two files to check when auditing "is there SQL outside storage" — mitigated by the
  contract tests being identical in shape, and by `test_only_storage_writes_sql` scanning
  `api/`, not `storage/`, so it already covers whichever module answers a given route.
- No email verification, no password reset, no rate limiting on login attempts — out of
  scope for Day 5 exactly as PLAN's Day 5 description names ("Email is out of scope for v1
  — no notifications yet") and left as an explicit debt rather than a silent gap.

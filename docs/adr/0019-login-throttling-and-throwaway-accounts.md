# ADR-0019: Login throttling, an explicit Secure cookie, and accounts that are throwaway until email exists

**Date:** 2026-07-29 · **Status:** Accepted · **Amends:** [ADR-0017](0017-auth-sessions-argon2-csrf-double-submit.md) · **Implements:** Day 6 (PLAN.md)

## Context

ADR-0017's consequences named three scope cuts in one sentence: *"No email verification, no
password reset, no rate limiting on login attempts — out of scope for Day 5 … left as an explicit
debt rather than a silent gap."* Day 5 was right to cut them; Day 6 deploys the thing publicly,
and deploying is what turns a named debt into real exposure.

A fourth problem was found while preparing the deployment, and it is the most serious of the four
because it fails silently: `_set_session_cookies` computed `secure = request.url.scheme == "https"`.
Behind Caddy, the scheme uvicorn sees is the `http` of the proxy's hop. Nothing enabled
`--proxy-headers` and nothing set `trusted_proxies`. **A TLS deployment would have issued session
cookies without `Secure`, with no error and no log line** — the exact failure the session prompt
said to check end to end rather than assume.

## Decisions

**1. Login throttling is a delay, not a lockout.** Five failures per email and fifty per address
within fifteen minutes, then 429 with `Retry-After`. Locking an account after repeated failures is
the obvious design and is wrong here: anyone could lock anyone else out by guessing badly at their
address, which turns the defence into a denial-of-service against the person it protects. A delay
that clears on success has no such property.

The two counters exist separately because they stop different attacks. Counting only by email lets
one host spray many accounts. Counting only by address lets a botnet grind one account. The
per-address limit is ten times looser because one address is legitimately many people — an office,
a campus, any NAT — while one email is one person.

**Failed attempts against unregistered addresses are counted too.** Otherwise probing for which
addresses exist would be the one unthrottled operation on the endpoint.

**2. `login_attempts` records failures only, and is not an audit log.** No success rows, no user
agent, no session link; a successful login deletes the account's rows. What it holds is the tail of
an ongoing guessing run. An audit log of who signed in when is a different feature with different
retention questions, and conflating them would answer neither well.

**3. The unknown-email path now runs argon2 against a dummy hash.** It used to return 401 before
any key derivation, so "no such account" was measurably faster than "wrong password" despite the
two being worded identically — an account-enumeration oracle that the careful wording had hidden
rather than removed. Measured after: 43.8 ms against 41.9 ms, a ratio of 1.05.

**4. The `Secure` cookie flag is configuration, not inference.** Two changes, because either alone
leaves the failure silent:

- uvicorn runs with `--proxy-headers` and Caddy sets `trusted_proxies`, so `request.url.scheme` is
  the client's scheme rather than the proxy hop's. This makes `auto` correct behind a proxy.
- `USC_COOKIE_SECURE` (`auto` | `true` | `false`) exists anyway, and production sets `true`. If the
  proxy configuration ever regresses, the cookie must not silently downgrade with it.

The setting lives in `params.py` rather than `db/config.py` because cookie policy is an HTTP
concern and `api/` may import nothing from `db/` but the session factory
(`tests/test_architecture.py`).

**5. Password reset and email verification stay out, and this records the consequence plainly:
accounts are throwaway until email exists.** There is no reset, no verification, and no recovery —
a forgotten password means making another account. PLAN puts email out of scope for v1 ("Email is
out of scope for v1 — no notifications yet"), and implementing reset means adopting an email
provider, its deliverability, and a token lifecycle, all ahead of plan and all to serve a demo
whose accounts hold a list of bookmarks. The honest thing is to say so where a person signing up
can read it, not to leave it as a discovery.

## Consequences

- Guessing a single account's password is limited to five attempts per fifteen minutes, and there
  is no way to use that limit to lock a real person out.
- A shared address gets a shared budget. Fifty failures per fifteen minutes is generous for an
  office and low for a botnet, but the tradeoff is real and the number is a guess informed by
  nothing but judgement — it is the one figure here most likely to need revisiting under load.
- `login_attempts` grows during an attack and is only cleaned by `purge_login_failures`, which
  nothing calls on a schedule yet. The window makes stale rows harmless to *correctness* — they
  fall outside every query — but not to size. A periodic purge is owed.
- Two bugs surfaced while wiring this up and are fixed here rather than filed:
  the `HTTPException` handler discarded `exc.headers`, so `Retry-After` never reached the client;
  and expired sessions were ignored on read but never deleted, so `auth_sessions` grew without
  bound. Presenting an expired cookie now sweeps them.
- Tests that deliberately fail logins share one client address, so the per-address counter
  accumulates across them. `tests/test_auth.py` purges the table around every test. This is a real
  property of the design, not a test artefact: anything behind a single egress address shares a
  budget.

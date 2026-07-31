# ADR-0034: A feature that is built and switched off says so where its control would be

**Status:** Accepted
**Date:** 2026-07-31
**Related:** [ADR-0017](0017-auth-sessions-argon2-csrf-double-submit.md) (the account layer),
[ADR-0019](0019-login-throttling-and-throwaway-accounts.md) (why accounts are not ready)

## Context

Two features are in this repository, tested, and should not be offered to a reader yet.

**Accounts** (ADR-0017) are complete — argon2, server-side sessions, CSRF, watchlists, per-account
settings — and carry a gap ADR-0019 named deliberately rather than left to be discovered: **no
email verification and no password reset**. An account is unrecoverable the moment its password is
forgotten. That makes offering one worse than not offering one.

**Bulk downloads** do not exist as a route at all, but the corpus does (9.7 GB of OLRC zips,
mirrored under ADR-0013) and readers reasonably expect a site built from bulk data to offer it.

## Decision

**Keep the controls, in the places working ones would be, and have them explain themselves.
Gate the behaviour on one build-time constant per feature in `frontend/src/lib/features.ts`.**

- `ACCOUNTS_ENABLED = false` removes the navbar's account island, the Watch button, and the login,
  signup and settings forms — and puts a shared explanation in each of those four places instead.
  `= true` restores all of it; nothing server-side is touched, and `tests/test_auth.py` and
  `tests/test_watchlists.py` still run against the live routes.
- `DOWNLOADS_ENABLED = false` renders a navbar control saying what bulk downloads will be, and
  linking to OLRC's own downloads in the meantime.
- One copy of the wording per feature, in `features.ts`, read by the navbar control and the
  page-sized one. Four copies of a promise drift into four different promises.

**The control is an ordinary enabled `<button>` — neither `disabled` nor `aria-disabled`.**

This is the part that took two attempts. `disabled` removes it from the tab order and refuses
focus, which hides the explanation from exactly the readers least able to guess at it.
`aria-disabled="true"` was the fix for that and is also wrong: Playwright refused to click it —
*"element is not enabled"* — and the refusal is correct. The button is not disabled. It has an
action, it performs it, and it performs it every time. What is unavailable is the *feature it
names*, and announcing "this control does nothing" about a control that does something is a
falsehood told to screen-reader users only.

So the unavailability is carried by things that are true: the word "soon" beside the label, a
sentence in `title` for a pointer that hovers, and a visually-hidden phrase for anyone who gets
neither. The greyed appearance is styling, not semantics.

**No JavaScript.** The panel is a `popover`, which supplies the top layer, `Escape` and light
dismiss for free — the same platform feature `CitePreview` is built on (ADR-0024), in its simplest
form. Both mechanisms the request asked about are present and neither costs a kilobyte.

## Alternatives rejected

**Delete the code.** Re-enabling becomes rewriting, and ADR-0017 and ADR-0019 would then describe
nothing that exists.

**Leave the controls live and let them fail.** A "Sign up" that 500s, or that creates an account
nobody can recover, is worse than no sign-up.

**Remove the controls silently.** A reader who used the watchlist last month finds it gone, with
nowhere to ask why — and "gone" and "not on yet" are different facts.

**An environment variable rather than a constant.** Reader pages come from a shared cache
(ADR-0018); a value that could differ per request would have to be varied on. The site either
offers accounts or it does not.

## Consequences

- `/app/login`, `/app/signup`, `/app/settings` and `/app/provisions` stay reachable and render the
  explanation rather than 404ing, so a bookmark lands somewhere that answers.
- The API routes behind all of it remain mounted and unauthenticated-by-default as before. **This
  is a UI switch, not a security control** — `POST /api/v1/auth/signup` still works for anyone who
  calls it directly. Turning the routes off is a separate decision and is not made here.
- Two islands stop shipping on every page (`AuthNav`, `WatchButton`), which removes two
  `/api/v1/auth/me` requests per page view. A hidden island still runs; not rendering it is what
  saves the request.
- The navbar gained two items, which pushed the wrapping nav in the 40–64em band onto another row:
  `--sticky-h` measured 386px against a 352px token, so every anchor jump in that band was landing
  34px behind the bar until the token was corrected to 25rem. **Adding a nav item is a change to
  that number** — the token's own comment says so, and this is the second session to learn it.

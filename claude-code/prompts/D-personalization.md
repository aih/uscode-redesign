# Workstream D — Personalization, watchlists, alerts

Accounts, watchlists and bulk downloads are **built and tested but switched off in the reader**
(ADR-0034), and the site says so where the controls would be. The blocker is recorded and honest:
**no email verification and no password reset** (ADR-0019). Do these in order; turning the UI on
before D1 ships a support burden, not a feature.

## D1 — Email, and therefore accounts

Transactional email (verification + password reset), rate-limited, with the token lifetimes and
the abuse story written down. Then a signup/login/reset flow that meets A8's error-identification
and status-messaging rules, and an ADR amending ADR-0019 and ADR-0034 to record that the switch is
being flipped and what now exists that did not.

Note the open API surface while you are there: `POST /api/v1/auth/signup` already works for a
direct caller regardless of the reader's switch — ADR-0034 is a UI decision, not a security
control. Decide deliberately whether that stays true.

## D2 — Watchlists and release alerts

- Wire the general multi-list CRUD at `/api/v1/watchlists` to a real page; today only the
  default-list convenience endpoints have UI.
- Watch a provision, a section, a chapter or a title. Watch **at an identifier**, not a guid — a
  guid pins (provision, release) and is never cross-release identity (ADR-0003). Getting this
  backwards is the most likely bug in the workstream.
- Alerts ride the existing daily poll: `ingest check` writes a `source_checks` row and runs the
  load chain only when OLRC publishes (ADR-0036), and `titles_affected` says which titles moved.
  An alert fires when a watched identifier's text actually changed — dedupe on
  `content_key`, not on the release point, or every watcher gets mail at every release
  (91% of stored text is unchanged; ADR-0007).
- Every alert links the redline that shows what changed (B5), and states the release point and its
  currency date.
- A per-user digest cadence (immediate / daily / weekly) and a working unsubscribe.

## D3 — Before a second instance exists

`CLAUDE.md`: *"the rate limiters are per-process state — honest for ADR-0020's single box and wrong
for a second instance."* Alerts and accounts are the features most likely to force horizontal
scale. Move the limiters to a shared store behind the same interface, keeping the single-box
default, and amend ADR-0029.

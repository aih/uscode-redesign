# ADR-0044: Release context belongs in the chrome, and the switcher keeps your place

**Status:** Accepted — supersedes `Provenance.astro`
**Date:** 2026-08-04
**Related:** [ADR-0018](0018-cache-immutably-only-when-the-release-point-is-pinned.md) (the pinned /
unpinned distinction the "Newest" option turns on), [ADR-0043](0043-one-navigation-chrome-on-every-page-that-is-a-place-in-the-code.md)
(the navigation half of the same chrome), [ADR-0029](0029-request-identity-and-rate-limits.md) (the
middleware this adds a redirect to)

## Context

This site's whole claim is that any provision can be read at any release point. The reader therefore
has to be able to answer "which text am I looking at" without inferring it — and had to infer two of
the four parts.

`Provenance.astro` printed the release point, its currency date, the `not`-law caveat and the
served-from note as grey meta text under the section heading. What it never printed is **whether the
label is the current law**. A page pinned to `119-99` and a page showing the text in force render
identically apart from a label the reader has to recognise, and recognising it means knowing the
inventory. That is the one fact a reader most needs and the one the page did not state.

The switcher had a worse defect. Its form action was built from `section.identifier`, so switching
release on `/app/us/usc/t16/s45f/c/5` submitted to `/app/us/usc/t16/s45f`: the reader asked to move
in time and was moved in the text as well, losing the provision they were reading. ADR-0001's whole
position is that a provision is shown in the context of its section; dropping it on a release switch
undoes that at the moment the reader is comparing versions.

It also offered one of the three ways to ask. `?release=` was a menu; `?date=` and "whatever is
newest" were URL syntax documented in the guide and available nowhere in the interface.

## Decision

**Four facts in a band at the top of every page that shows a provision, and a switcher under it that
offers all three ways to ask.**

`ReleaseContext` replaces `Provenance` and states:

1. the release point and its currency date;
2. **whether it is the newest** — `newest`, or `not the newest` with a link to the current text at
   the same provision. Marked by border as well as by colour (WCAG 1.4.1);
3. the caveat on a `not` label (gotcha 5);
4. the API's own served-from sentence when the answer came from an earlier ingested release point
   (gotcha 10).

`ReleasePicker` becomes two GET forms — a release menu whose first entry is *Newest — follows new
releases*, and an *As of date* box. **Two forms rather than one** because `?release=` beats `?date=`
in `resolve_release`, so a single form would submit both and silently ignore whichever the reader had
just set. Both post to the **requested** identifier, so the provision survives the switch.

Both remain plain forms with no JavaScript, which is what makes their output a URL worth pasting.

## Where it sits, and why not in the sticky bar

The task asked for this in the chrome. The switcher was in the chrome — in `.contextbar`, inside the
sticky stack — and the date field would not fit. Measured on a section page before the change:

| width | sticky stack | `--sticky-h` | headroom |
|---|---|---|---|
| 375px | 45px | 52px | 7px |
| 700px | 381px | 400px | 19px |
| 1280px | 249px | 304px | 55px |

The date form costs about eighty pixels. `--sticky-h` is what `scroll-margin-top` spends, so raising
it is charged to every deep-linked provision on the site, in a band `docs/backlog.md` already flags
for occupying 37% of a landscape-tablet viewport. So the switcher moved out of the stack and down to
the facts it changes, and the **release point stays pinned as text** in the context bar — the answer
to "as of when" is what has to be on screen at every scroll position, not the means of changing it.

Moving it out took the headroom to 89px at 700px and 85px at 1280px.
`tests/e2e/sticky.spec.ts` now asserts that spare capacity, so a future addition that eats it has to
raise the token deliberately rather than by accident.

## A redirect, in middleware

The "Newest" option carries an empty value, because an absent `?release=` is already how the whole
site spells "newest". A GET form submits every control it has, so choosing it produced
`/app/us/usc/t16/s45f?release=`. That answers correctly — `lib/api.ts`'s `qs()` drops empty
parameters — and it is also the URL the reader is invited to cite. `frontend/src/middleware.ts`
redirects once to the clean form. One place, rather than every page learning to strip it.

## Costs

**The release menu is every release point for the title.** 115 options for Title 16 against the local
corpus and 381 corpus-wide, in the markup of every section page. That was already true of the old
picker and is not made worse here; it is written down because it is the obvious thing to fix next and
nothing else records it.

**The chrome now depends on `fetchReleases`.** It was previously the picker's own call and could have
been dropped with the picker; the band needs it to answer "is this the newest", since that is
`releases[0].label === selected`. It is not allowed to fail silently — a page that cannot say whether
it is current is the failure this ADR exists to prevent — so it stays in the `Promise.all` that
rejects.

**Two pages deliberately have no band.** `/app/versions` spans every release point at which the
section changed and `/app/diff` is about two of them, so neither is reading one, and a bar naming a
single release there would answer a question the page does not ask. Both carry the breadcrumb
(ADR-0043). This is a narrower reading of "every reader page" than the task asked for, and it is
deliberate.

**One new scenario verb.** `fill` cannot drive a `<select>`, so the guide's DSL gained `select`
(`frontend/scripts/scenarios.mjs`). ADR-0038 keeps that vocabulary deliberately small; this is the
tenth verb, and it was added because the claim "switching release keeps the provision you were
reading" is precisely the one that has to be executable.

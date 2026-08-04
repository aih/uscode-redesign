# ADR-0042: Contrast is computed from the tokens, and boundaries are not dividers

**Status:** Accepted
**Date:** 2026-08-04
**Related:** [ADR-0027](0027-light-by-default-dark-by-choice.md) (two palettes, so every colour
claim is two claims — and decision 1 of it, which this deliberately does not change),
[ADR-0039](0039-accessibility-is-a-ratchet-in-the-browser-suite.md) (the scan this complements),
[ADR-0011](0011-astro-uswds-frontend-at-app.md) (USWDS, which supplies most of the colours nobody
here chose)

## Context

The reader has two palettes and no measurement of either. ADR-0039's axe scan covers what is *on a
scanned page in a scanned state*, which turns out to be a different set from "every colour pair the
design uses" in both directions — and the gap runs both ways, which is the reason this is a separate
piece of work rather than more of that one.

The scan misses pairs no scanned route happens to render. No route in the matrix carried a status
badge, so nothing had ever measured one.

A token audit misses colours that are not tokens. The worst failure on the site was USWDS's own
`.usa-nav__link` keeping its light-theme grey inside a dark panel — `#565c65` on `#1c1d1f`, 2.5:1, on
**every reader page**, at 320px and 375px only, clean at 1280px, which is why it survived. No token
file contains either of those values.

## Decision

**`scripts/contrast.py` computes every declared pair from the token block, in both themes, and exits
non-zero on a failure.** The token values are read from `frontend/src/styles/site.scss`; the list of
*pairs* is declared in the script, because which colour is painted on which is a fact about the
design rather than about the file. `docs/verification/contrast.json` is the artifact — 17 pairs, 34
checks.

**`--rule` is split.** SC 1.4.11 asks 3:1 of "visual information required to identify user interface
components", which is a field's edge and is not a divider between two paragraphs: remove the divider
and the page still says everything it said. Holding both to 3:1 puts every hairline on the site at
`#949494` or darker — a visibly heavier reader bought for no conformance gain. So `--edge` is the
half that carries meaning and is held to the ratio (4.71:1 at its worst, on a dark form field), and
`--rule` stays decorative, measured and reported at 1.15–1.89:1 with `"decorative": true` beside it.
Reported rather than dropped, so the number is on the record and the judgement is arguable.

**Status badges carry a border treatment as well as a colour.** The badge's *text* was already the
information — "repealed" and "omitted" are different words, printed verbatim (gotcha 13: the status
set is not closed, so the word is never mapped through an enum). What colour adds is emphasis, and
emphasis is exactly what monochrome loses. Each known status now differs in border style — solid,
dashed, double — and unknown ones keep the plain pill and their word. A border rather than an icon,
because CSS `content` is announced by some screen readers, and "× repealed" would be noise read to
the readers who least needed the help.

**Forced colours are handled where meaning lives in a painted surface**: the status badge, the
highlighted provision (`Highlight`/`HighlightText`, the system's own pairing for exactly that), the
`<select>` whose chevron is a background image USWDS draws and a forced-colors reader may not get,
the redline's change bars, and the copy buttons, whose deliberate 45% quietness cannot survive a
palette that has no opacity.

**`prefers-reduced-motion` is honoured globally** rather than at the two places that already did it,
and includes `scroll-behavior` — a smooth-scrolled anchor jump is motion the reader did not ask for,
on every deep link into a provision.

## What this measured and fixed

Five failures the tokens found or the scan found, each now passing and each removed from
`docs/a11y/known-violations.json`:

| where | was | now |
|---|---|---|
| USWDS mobile nav, dark | 2.5:1 | inherits `--ink` |
| copy column's outline button, dark | 2.71:1 | inherits `--link` |
| repealed / omitted badge, dark | 2.25:1 | 8.12:1 via `--danger-ink` |
| `.usa-alert` body, dark | 1.12:1 | inherits `--panel`/`--ink` |
| guide code blocks | 1.11:1 | Shiki's own background |
| `/app/docs` method badges | 4.49:1 | 4.99:1 |

The artifact went from 41 route/rule pairs over 2,251 nodes to **8 over 1,780**; the 8 that remain
are the vendored Swagger UI and ReDoc bundles and two entries owned by A4.

Two of these were bugs rather than choices. The `.usa-alert` background is on `__body`, not on the
outer element — the identical shape to ADR-0027's footer note, made a second time. And
`.endpoint__method` took its *text* colour from `--panel`, a token that inverts between themes, while
its background was a fixed saturated colour: near-black on dark green in the dark theme. Both are the
same underlying error, which is using a token for a role it was not defined for.

## What was declined

**A7 asked to "honour `prefers-color-scheme` on first visit while keeping ADR-0027's light default
explicit".** Those two halves contradict each other: honouring the OS preference on a first visit
*is* not defaulting to light. ADR-0027 decision 1 removed exactly that behaviour, in response to a
reader asking why the site was in dark mode, and `theme.spec.ts` carries a test named "the site is
light even when the OS asks for dark".

Declined, and confirmed with the maintainer rather than assumed. WCAG 2.1 AA requires neither
direction — 1.4.3 and 1.4.11 are about the contrast of what is shown, not about which palette is
chosen first — so nothing in this workstream's own target depends on it. The default stays light; the
toggle stays the only route to dark; the preference stays in `localStorage` and out of the cache key.

## Costs

**The pair list is hand-declared and can go stale.** The script reads the token *values* from the
stylesheet, so a changed hex is caught — but a new token painted on a new surface is a pair nobody
added, and the script will not miss it, because it does not know to look. The axe scan is the
backstop for that, and only on routes and states the matrix covers.

**Four badge colours are now hard-coded** rather than tokenised. `.endpoint__method`'s backgrounds
are fixed because they are semantic method colours that must not move with the theme, which means
they are also outside `contrast.py`'s reach — their values live only in the stylesheet and in the
axe scan.

**`--rule` failing 1.4.11 on paper is a judgement.** A reviewer who disagrees that a note's left
border is decorative has a real argument, and the numbers to make it are in the artifact.

**`forced-color-adjust: none` is used twice** — on the status badge and the highlighted provision.
Both override the reader's chosen palette in a place where the meaning is the colour, which is what
the property is for and is still an override of an accessibility preference.

**The scan grew by seven scans.** `/app/us/usc/t16/s688` joined the matrix because nothing in it
carried a status badge, which is how a badge went unmeasured until a token audit found it.

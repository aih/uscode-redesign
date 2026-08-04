# ADR-0041: The preview card is reachable, and says when it fails

**Status:** Accepted — amends [ADR-0024](0024-reference-previews-render-server-side.md)
**Date:** 2026-08-04
**Related:** [ADR-0029](0029-request-identity-and-rate-limits.md) (the 429 this now shows),
[ADR-0039](0039-accessibility-is-a-ratchet-in-the-browser-suite.md) (the scan that found the first
of these)

## Context

ADR-0024 built the hover preview. Its decision 4 was **`aria-hidden` on the card**, on the reasoning
that the card's content duplicates the link's own `title` and that "a screen reader announcing a
paragraph of statutory text on every reference in a forty-reference section would be worse than
useless".

Alongside it, and recorded nowhere but in a comment in `CitePreview.astro`, the island **returned
silently when a preview could not be fetched**: "a failed preview is not an error the reader needs to
see: the link still works, which is the whole fallback". That it was never an ADR decision is part of
the problem — it is a user-visible behaviour that no one signed.

The first is wrong as built rather than wrong as reasoned. The card carried `aria-hidden="true"`
*and* `tabindex="0"` — focusable and hidden from assistive technology at the same time. That is axe's
`aria-hidden-focus`, and it is the one combination with no defensible reading: a keyboard user can
put focus somewhere their screen reader will not describe. It was invisible to every scan that only
loads pages, and the open-state scan added by ADR-0039 found it on the first run.

The reasoning behind it does not survive contact with the mechanism either. Removing `aria-hidden`
does not make anything announce. Nothing moves focus on open and there is no live region, so the card
is silent until a reader goes to it deliberately. The alternative ADR-0024 actually rejected —
`aria-describedby` pointing at the live card — *would* have announced, and rejecting it was right;
`aria-hidden` was applied as though it were the same decision, and it is not.

The second is a fair trade stated one-sidedly. A card that silently declines to open is
indistinguishable from a feature that is broken, from a citation with nothing behind it, and from a
page that has stopped responding. The link does still work — but nothing on screen says so, and the
reader has been given no next step. Since ADR-0029 the preview endpoint is rate-limited at 60 per
minute with a burst of 5, so a reader moving down a dense section meets a 429 in normal use, and
what they see is nothing at all.

## Decision

**The card is a non-modal dialog the reader can reach and leave, and a failure is shown rather than
swallowed.**

- `aria-hidden` is gone. `tabindex="0"` stays — the body scrolls, and a scrollable region with no
  focusable children is unreachable by keyboard without it (`scrollable-region-focusable`). The card
  takes `role="dialog"` and an `aria-label` set per reference when it opens, so focus arriving
  announces the provision rather than "dialog".
- **Tab from the trigger moves into the card**, because a popover in the top layer at the end of the
  document is not in the reader's tab order in any useful sense. **Escape closes it and returns focus
  to the reference**, without scrolling. Tabbing past the end of the card does the same.
- **A dismissal latches.** Escape returns focus to the trigger, which is a `focusin` on the trigger,
  which is what opens the card — so without a latch the card the reader just closed reopens 300ms
  later and Escape does nothing. The latch clears as soon as attention moves to another reference.
- **A failure renders "Preview unavailable" and a link to the citation.** A 429 says so specifically.
  An `AbortError` stays silent, because that is the island superseding its own request and no reader
  asked for it.

Touch is unchanged and was already right: the feature is behind `(hover: hover) and (pointer: fine)`,
so a tap opens the citation and no card ever appears. `preview.spec.ts` already asserted it.

## Costs

**ADR-0024's decision 4 now reads as superseded rather than current.** Anyone reading it without this
file will implement the wrong thing. That is the standing cost of amendment-by-new-ADR; the header
and the decision itself both point here.

**The dismissal latch is state, and state is where the bugs are.** A reference the reader dismissed
behaves differently from one they have not, until they look elsewhere. The alternative — Escape that
does not work from the keyboard — is worse, but this is a real asymmetry that no test would catch if
the clearing rule were wrong in some path nobody tried.

**A failure message costs a card where there used to be none.** A reader whose network is failing now
gets a small box on every citation they touch, saying so each time. That is louder than silence and
is the point, but it is louder.

**The 429 message names a cause the reader cannot act on.** "Too many previews just now" is true and
is not useful advice; the useful part is the link beneath it. Retry-After is not surfaced.

**`role="dialog"` on something that is not modal** will read as a dialog to assistive technology
without behaving like one — no focus trap, and the page behind it stays live. That is the ARIA
Authoring Practices' non-modal dialog and it is the closest available role, but "dialog" sets an
expectation of modality that this deliberately does not meet.

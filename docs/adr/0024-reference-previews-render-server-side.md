# ADR-0024 — Reference previews render server-side as HTML fragments

- **Status:** Accepted
- **Date:** 2026-07-29
- **Context:** Session 10 (UI refresh before deploy), BUILDLOG 024

## Context

A section of the Code can carry forty cross references. Following one to find out
whether it matters costs a page load and your scroll position — in a document
where the reading position *is* the work. Since ADR-0015 a reference has carried
`title="§ 523. Exceptions to discharge"`: the heading, which answers "what is
this called" and not "does this change what I just read".

## Decision

**1. The preview is rendered by the server and delivered as HTML.**
`/app/preview/us/usc/…` returns a fragment produced by the same
`frontend/src/lib/uslm.ts` the section page uses.

This is the load-bearing choice. `uslm.ts` is the one module outside the parsers
permitted to know USLM element names (architecture rule 5); it runs on
`@xmldom/xmldom` and cannot be bundled into a browser script without moving
presentation into the client. Sending rendered HTML means **no USLM renderer
ever reaches the browser**, no second renderer to keep in sync, and no new API
endpoint — the reader already knows how to fetch a section and render it, and
this is that, truncated.

**An endpoint (`.ts`), not a page (`.astro`).** Astro prepends `<!DOCTYPE html>`
to a page, which is exactly wrong inside a `<div>`.

**A miss returns 200 with an explanatory fragment**, not 404. The island has
nothing useful to do with an error status except swallow it, and "not published
at this release point" is worth showing to someone who just asked.

**2. The card is built from platform primitives** (ADR-0022): `popover` for the
top layer, Escape and light dismiss; CSS anchor positioning for placement, with a
measured `getBoundingClientRect` fallback because Safari 18.2–18.3 has `anchor()`
but not `@position-try`. One island, ~3 KB.

Being in the top layer also means the card always paints above the sticky bar,
with no `z-index` contest to lose.

**3. WCAG 2.1 SC 1.4.13 is the acceptance bar**, and each clause is a named
mechanism with a named e2e test:

| Clause | Mechanism | Test |
|---|---|---|
| **Dismissible** | `Escape` closes without moving the pointer | `SC 1.4.13 dismissible` |
| **Hoverable** | 250 ms close delay, cancelled when the pointer enters the card | `SC 1.4.13 hoverable` |
| **Persistent** | stays until dismissed, pointer leaves both, or focus moves | `SC 1.4.13 persistent` |

Hoverable is the clause most hover previews fail, and the one a scrollable card
cannot do without. Focus opens the card too — 1.4.13 covers focus as well as
hover, and a keyboard reader has the same question about a cross reference.

**4. The card is `aria-hidden="true"`.** Its content duplicates the link's own
`title` and is one click away in full. A screen reader announcing a paragraph of
statutory text on every reference in a forty-reference section would be worse
than useless.

This is the decision most worth disagreeing with. The alternative —
`aria-describedby` pointing at the live card — gives assistive-technology users
the same content sighted users get, and was rejected because "the same content"
here means the card's entire body injected into the accessibility tree on focus.
The `title` attribute remains, so a screen-reader user gets the heading exactly
as before this change.

**5. Touch navigates.** The whole feature is behind
`(hover: hover) and (pointer: fine)`. Hover does not exist on a phone, and every
workaround — first-tap-opens, long-press — either fights the OS or breaks the
expectation that a link is a link. A tap is a navigation; the `title` attribute
still carries the heading.

## Consequences

- `renderRef` emits `data-cite` (the identifier, so the island never un-prefixes
  `/app`) and `data-cite-release`. The release rides along so a preview is read
  at the same release point as the page quoting it — without it, a section read
  at 119-99 would show its cross references as they stand today, quietly mixing
  two vintages of the law, which is the one thing this project exists to avoid.
- `title` stays on every reference. It is the no-JavaScript fallback, what a
  screen reader announces, and what a touch device shows. Removing it would be a
  regression on three fronts, so a Vitest case asserts it survives alongside
  `data-cite`.
- References *inside* a card do not open cards of their own. One level of
  preview; the links in it navigate.
- **A new unauthenticated route that fans out per hovered citation.** The 300 ms
  hover intent, the per-page `Map` cache and `AbortController` hold it down, and
  it is far cheaper than the diff endpoint — but the standing "rate-limit before
  advertising the URL" debt in `docs/verification/loadtest.json` now covers two
  routes, not one.
- The preview budget is **4,000 characters**, not the 1,400 it started at. 1,400
  is less than the card's own 22rem can display, which made the scroll area
  decoration and cut every preview off mid-thought — a preview that cannot tell
  you whether the cited provision matters is a tooltip with extra steps.

## Alternatives considered

- **Appica's Preview Card**, or any React hover-card. Rejected in ADR-0022: it
  requires `uslm.ts` to emit React elements.
- **Fetching the section JSON and rendering in the browser.** Puts a USLM
  renderer in the client, breaking architecture rule 5, and ships the whole
  section's XML to preview two paragraphs of it.
- **A new `/api/v1` preview endpoint.** The rendering lives in the frontend by
  ADR-0011; an API that returned HTML would be the wrong surface returning the
  wrong media type.

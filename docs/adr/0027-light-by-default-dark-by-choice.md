# ADR-0027 — Light by default, dark by choice, stored on the client

- **Status:** Accepted
- **Date:** 2026-07-30
- **Context:** Session 11, BUILDLOG 025

## Context

`site.scss` had carried a dark palette since the reader was built, gated on

```scss
@media (prefers-color-scheme: dark) { :root { … } }
```

with `color-scheme: light dark` on the root. Most people's laptops report dark,
so most visitors were shown the United States Code as light text on near-black
without ever asking for it — which is what prompted this: *why is the app in
dark mode?*

Two things were wrong with it beyond the default.

- **There was no way out.** No control anywhere on the site changed it. The
  reader's only recourse was to change their operating system.
- **The dark palette was three rules deep.** `body`, `.usa-header`/`.usa-footer`
  and `a` were re-coloured; USWDS's controls, tables, summary boxes and the
  footer's *inner* sections were not, because USWDS paints those white
  explicitly. The citation box and the release picker were the brightest things
  on a dark page, and the footer was a white slab.

## Decision

**1. Light is the default at every OS setting.** A statute is a document, and a
document's page is white until someone says otherwise — it is what the Code
looks like in print and on OLRC's own site. `prefers-color-scheme` no longer
selects anything; the dark palette hangs off `:root[data-theme="dark"]`.

**2. Dark is one control in the header** (`ThemeToggle.astro`), the reader's
fourth island and about 700 bytes. It sets `<html data-theme>` and writes
`localStorage["usc-theme"]`. The accessible name states what the click will do
("Switch to dark mode") rather than pairing a changing label with `aria-pressed`.

**3. The preference is client-side, never a cookie.** This is the load-bearing
part. Every reader response carries a cache policy (ADR-0018) — `immutable` for
a pinned release, `max-age=300` + ETag otherwise — and those bytes are identical
for every visitor. A theme cookie would put `Vary: Cookie` on all of it and
trade a shared cache for a colour preference. The document served is the same;
the client decides how to paint it.

**4. The attribute is stamped in a blocking `<head>` script**, inline in
`Base.astro`. Light needs no script at all, so the common case pays nothing; a
reader who has chosen dark needs the attribute set *before* first paint or every
navigation flashes white. An external module would be a network round trip in
front of the first paint of every page.

**5. `color-scheme` moves with the attribute**, so the UA themes what CSS cannot
reach: scrollbars, focus rings, and the dropdown a `<select>` opens.

**6. The dark palette was extended to what USWDS actually paints** — inputs,
selects (including repainting the chevron SVG, which is drawn in ink and was
invisible on a dark field), tables, summary boxes, and the footer's primary and
secondary sections rather than just `.usa-footer`.

## Consequences

- Four Playwright tests, all of them running with the OS set to dark, because
  that is the case that was broken: the page is white anyway; the toggle goes
  both ways; the choice survives a navigation *and* is stamped by the head
  script; and the toggle costs the sticky chrome no height.
- That last one is not incidental. The control shares a flex row with the
  citation box (`.navtools`) precisely because a second block in the navbar
  would add ~44 px to the sticky stack between 40em and 64em, and `--sticky-h`
  is what `scroll-margin-top` spends (ADR-0024's geometry). Measured: the top
  bar is 280 px at 700 px wide, unchanged, against a token of 288 px.
- No-JS readers get light, and no dead control: the button is rendered `hidden`
  and un-hidden by its own script.
- A reader with `localStorage` blocked can still toggle for the current page;
  the choice just is not remembered.
- **Not done:** a third "follow the system" state. Two states are what was
  asked for, and a tri-state control needs a label that explains itself.

## Alternatives considered

- **Keep `prefers-color-scheme` as the default and let the toggle override.**
  Tempting, and it is the usual advice — but it makes the site's appearance a
  property of the visitor's machine rather than a decision, and the complaint
  that started this was precisely that. The OS signal is still available if a
  "system" option is ever added.
- **A cookie, so the server renders the right theme.** Correct with no flash and
  no head script, at the price of `Vary: Cookie` on the whole cached reader
  (ADR-0018). Rejected on cost.
- **`class="dark"` instead of `data-theme`.** Same mechanism; the attribute
  reads as configuration rather than styling, and it leaves room for a third
  value.

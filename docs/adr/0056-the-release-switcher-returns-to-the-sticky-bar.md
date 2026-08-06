# ADR-0056 — The release switcher returns to the sticky bar, as a disclosure

- **Status:** Accepted
- **Date:** 2026-08-06
- **Context:** Session 32, asked for directly — the release block takes too much space and repeats
  what the bar already says; and a counterpart to `t` for the foot of the page
- **Amends:** [ADR-0044](0044-the-release-point-is-a-fact.md) (the switcher is pinned again),
  [ADR-0055](0055-navigation-inside-a-section-and-a-keyboard-map.md) (one more key in the map)

## Context

ADR-0044 split "as of when" in two. The sticky bar stated the release point:

```
Title 16 › CHAPTER 1 › SUBCHAPTER VI › § 45f          Release point 119-102not101
```

and the controls that change it sat in the page body, under the release band, above the section's
own heading — a menu, a date field and two Go buttons across the top of the reading column.

That split was decided on a measurement. `--sticky-h` is what `scroll-margin-top` spends, so every
pixel the chrome takes is a pixel of the viewport a deep-linked provision starts below. At 700px the
stack had 19px of headroom under the token and the date field cost about eighty, so keeping the
switcher pinned meant raising `--sticky-h` in a band already carrying 19rem of chrome.

What it cost is what this ADR is about. The release point is now written twice on every section
page, three lines apart — once in the bar and once as the switcher's own `Release point` label — and
the controls take about 180px off the top of the reading column on every section page, whether or
not the reader has any intention of moving in time. Scrolling past them loses them: the answer stays
pinned and the means of changing it does not.

## Decision

### 1. The switcher is a `<details>` whose summary is the release point

`ReleasePicker` moves back into `.contextbar` and becomes a disclosure. Closed, it is the line the
bar already carried:

```
Title 16 › CHAPTER 1 › SUBCHAPTER VI › § 45f          Release point 119-102not101 ▾
```

Open, it drops a panel holding the two GET forms unchanged — the release menu whose first entry is
*Newest — follows new releases*, the `MM/DD/YYYY` box, their labels, their buttons and the hint.

The measurement that moved this control out is answered rather than overruled. The summary is one
line where the release point was already one line, so the closed stack is the height it was and
`--sticky-h` does not move. The panel is `position: absolute`, so the open stack is the same height
too — asserted, at 700px and at 1280px, by `sticky.spec.ts`: `.contextbar`'s box is the same number
of pixels open as closed.

Native `<details>`, so this costs no script. The forms stay plain GET forms with no JavaScript, which
is what makes a switched release point a URL you can paste (BUILDLOG 007).

`.releaseblock` keeps `ReleaseContext` alone — the four facts, which are a statement and not a
control.

### 2. The disclosure is reachable at every width

`.contextbar__rp` is hidden below 40em: down there the context bar scrolls away with the rest of the
chrome, and the release band a few pixels below repeats it. That reasoning does not carry over to a
control. The switcher renders at every width, and below 30em the panel is pinned to the bar's own
edges rather than hung from the right edge of a summary that has wrapped.

The panel's containing block is `.rpswitch` at every width except that band, where `.rpswitch` goes
static and `.contextbar` goes relative. Below 40em `.topbar` is `display: contents` — the arrangement
that lets `.sectionbar` pin to the page rather than to a scrolled-away wrapper — so with nothing
between the panel and the root positioned, `top: 100%` would have put it a viewport height down the
document.

`z-index: 600` on the panel, above `.sectionbar`'s 500. In that same band the two are siblings in the
body's own stacking context and the section bar comes later in the document.

### 3. `b` goes to the foot of the page

One more row in `lib/shortcuts.ts`, under *Anywhere on the site*, and one more `case` in
`KeyboardNav`. `t` reaches `#main` — the top of the content, past the navigation, which is where the
skip link goes. `b` reaches the `<footer>` with `block: "end"`, so it lands on the end of the page
rather than on the top of the last element in it, and the site's own links are under the keyboard
when it arrives.

Nothing else changes: the key comes out of the same list the help dialog renders, `/app/design`
renders as a panel and the island receives as JSON, so a key that is printed is a key that fires
(`shortcuts.test.ts`).

## Consequences

**`Escape` does not close the switcher.** It closes the shortcut dialog and the hover card, both of
which own a script. A `<details>` does not, and giving this one an island to add `Escape` and
click-outside would put bytes on every route for a control the summary already closes. The panel is
dismissed by pressing the summary again, and by navigating, which is what the Go buttons do.

**A page that knows its release point and has no list to offer keeps the plain `<p>`.** The picker is
null when the releases call returned nothing, and the bar falls back to stating the release point as
text — `.contextbar__rp`, unchanged. `/app/design` renders it that way too.

**The a11y matrix gains a state.** Closed, the panel is not in the document, so the two labelled
controls and their buttons are markup no other scan reaches. `release-switcher-open` is the
eighth interactive state in `docs/a11y/routes.json`.

**The scenario vocabulary gains `expect: { inViewport: true }`.** `visible` is true of an element a
screen below the fold, which asserts nothing about a shortcut whose whole job is to scroll there.
`scenarios.mjs` validates it, `guide.spec.ts` runs it as `toBeInViewport`, and `describeStep` says
it in English for the guide's "How this is verified" box.

**`b` is one more single letter the page claims.** It joins `t c s n u j k [ ]`; as with those,
nothing fires while focus is in a text field, a `<select>` or anything `contenteditable`, and no
combination holding Ctrl, Alt or ⌘ is touched.

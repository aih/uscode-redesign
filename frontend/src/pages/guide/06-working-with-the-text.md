---
layout: ../../layouts/GuideLayout.astro
title: Working with the text
order: 6
summary: Copying a provision with its citation, reading a cross reference without losing your place, citing an exact text, and the reading settings the browser keeps.
covers:
  routes: ["/app/settings"]
  adrs: [3, 24, 27, 33, 41, 54]
---

## Copying a provision

Beside each provision inside a section is a copy control in the gutter. The section as a whole has
a **Whole section** button in the bar above the text, and beside that button a **mode** that says
what copying means:

- **Text** — the words alone.
- **Citation** — `16 U.S.C. § 45f(c)(5)`, computed by the server from the identifier.
- **Citation + text** — both, in the order you would paste them into a brief.
- **Link** — a URL carrying the release point the page is reading, so a link copied from a pinned
  page stays pinned. Pasted into anything that understands rich text, it arrives as a hyperlink
  labelled with the citation.

The mode is remembered. For the one-off exception, hold a modifier as you click: <kbd>Shift</kbd>
for the citation, <kbd>Alt</kbd> for both, <kbd>Ctrl</kbd>/<kbd>⌘</kbd> for a link — for that click
only, without disturbing the setting.

The copy controls need JavaScript. With scripting off the whole column is absent, gutter and bar
alike.

```scenario
id: copy-whole-section
title: Copy a whole section
demo: true
demoOrder: 110
needs:
  clipboard: true
steps:
  - goto: /app/us/usc/t16/s45f
    caption: Every provision has a copy control, and the whole section has its own button.
  - click: .copycol__whole
    caption: Choose what copying means — text, citation, both, or a link.
  - expect: { selector: ".copycol__status", contains: "Text copied" }
    caption: The page says what it copied, out loud, for a screen reader too.
```

**Copying does not include notes or source credits.** A designator and its sentence stay on one
line.

## Reading a cross reference without leaving the page

Hovering over a linked citation — or reaching it with
the keyboard — opens a small card with the cited provision's heading, status and opening words, and
a link to the whole thing.

The card is hoverable (you can move the pointer into it), dismissible with <kbd>Escape</kbd>, and
stays while you are pointing at it.

**From the keyboard**, focusing a citation opens the same card. <kbd>Tab</kbd> moves into it, so the
"Open full section" link and any citations inside are reachable; <kbd>Escape</kbd> closes it and puts
you back on the citation you started from, at the same place on the page. Tabbing past the end of
the card does the same. A card you have dismissed stays closed until you look at another reference.

**Previews need a hovering pointer.** The card is built only where the browser reports
`(hover: hover) and (pointer: fine)` — a mouse or a trackpad. On a touchscreen there is no card by
hover or by focus, and a citation opens as a link.

```scenario
id: preview-keyboard
title: Reach a preview and leave it again from the keyboard
steps:
  - goto: /app/us/usc/t16/s45f
    caption: Every citation in the text opens its preview on focus, not only on hover.
  - focus: a[data-cite]
    caption: Focus a citation and the card opens.
  - expect: { selector: "#cite-preview", visible: true }
  - press: Escape
    caption: Escape closes it and returns you to the citation.
  - expect: { selector: "#cite-preview", visible: false }
```

**When a preview cannot be fetched** the card says so and offers the citation instead of appearing
empty. Previews are rate-limited. Moving quickly down a section with many references can reach the
limit, and the message says when that is what happened.

```scenario
id: hover-preview
title: Read a cross reference without losing your place
demo: true
demoOrder: 120
steps:
  - goto: /app/us/usc/t16/s45f
    caption: Statutory text is full of references to other statutory text.
  - hover: a[data-cite]
    caption: Hover one and the cited provision comes to you —
  - expect: { selector: "#cite-preview", visible: true }
    caption: — heading, status and opening words.
```

## Citing an exact text

A section page carries two addresses. One is the **citation URL**
(`/us/usc/t16/s45f/c/5`) — stable across release points, and what you want in a brief that means
"this provision, as it stands".

The other is a **guid**: `/us/usc/?id=id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd`. A guid pins one
provision at one release point, so it needs no `?release=` and no date. It means *this exact text,
as it stood at this point in time*.

```scenario
id: guid-permalink
title: A guid resolves to one exact text with no release parameter
data: corpus
steps:
  - goto: /app/us/usc/?id=id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd
  - expect: { url: "/us/usc/t16/s45f" }
```

## Night mode

**Light or dark.** The **More** menu in the header holds the control, under **Display**. Light is
the default setting. The choice is kept in the browser and applied before the page paints.

```scenario
id: theme-toggle
title: Switch the site to dark
demo: true
demoOrder: 130
steps:
  - goto: /app/us/usc/t16/s45f
    caption: Light is the default setting.
  - click: .navdrop--more > summary
    caption: More holds the display switches.
  - click: .navdrop__list .theme-toggle
    caption: One control switches the theme.
  - expect: { selector: ".theme-toggle__label", contains: "Light" }
    caption: The choice is remembered, and lands before the page paints.
```

## Reading density

**Comfortable or compact.** A second control under **Display** sets how much law fits on the screen.
Comfortable is the default. Compact tightens the space between lines and between paragraphs and
sets the text a little smaller. Like the theme, the choice is kept in the browser and applied
before the page paints.

The column narrows with the text, so a compact page holds the same number of characters per line as
a comfortable one. On a long section compact is 11% to 16% shorter to scroll
(`docs/verification/measure.json`). On a short one, or one built mostly of tables, it makes no
difference or adds a percent or two: a narrower column gives a table more rows to wrap into.

```scenario
id: density-toggle
title: Switch the reading density to compact
demo: true
demoOrder: 135
steps:
  - goto: /app/us/usc/t16/s45f
    caption: Comfortable is the default setting.
  - click: .navdrop--more > summary
    caption: More holds the display switches.
  - click: .navdrop__list .density-toggle
    caption: The control beside the theme toggle switches it.
  - expect: { selector: ".density-toggle__label", contains: "Comfortable" }
    caption: The control now reads Comfortable, which is the way back.
```

**Links open in new tabs.** Cross references and search results open in a new tab by default.
[Settings](/app/settings) changes that to the same tab. It is stored on your account, which means it is currently a preference you can only
set if accounts are on — see the next chapter.

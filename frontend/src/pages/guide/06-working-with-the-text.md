---
layout: ../../layouts/GuideLayout.astro
title: Working with the text
order: 6
summary: Copying a provision with its citation, reading a cross reference without losing your place, citing an exact text, and the two settings the reader keeps.
covers:
  routes: ["/app/settings"]
  adrs: [3, 24, 27, 33]
---

## Copying a provision

Beside every identified provision is a copy control, and above them a **mode** that says what
copying means:

- **Text** — the words alone.
- **Citation** — `16 U.S.C. § 45f(c)(5)`, computed by the server from the identifier.
- **Citation + text** — both, in the order you would paste them into a brief.
- **Link** — a URL. Pasted into anything that understands rich text, it arrives as a hyperlink
  labelled with the citation.

The mode is remembered. For the one-off exception, hold a modifier as you click: <kbd>Shift</kbd>
for the citation, <kbd>Alt</kbd> for both, <kbd>Ctrl</kbd>/<kbd>⌘</kbd> for a link — for that click
only, without disturbing the setting.

There is also a **Whole section** button, which is a named button rather than a gutter icon,
because copying an entire section is a different act from copying a paragraph of it.

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

**What copying leaves out:** the notes and the source credit. Those are the OLRC's editorial
apparatus around the text, not the text, and pasting a section into a brief should not drag them
along. A designator and its sentence stay on one line, so the shape survives the paste.

## Reading a cross reference without leaving

Statutory text is full of references to other statutory text. Hovering one — or reaching it with
the keyboard — opens a small card with the cited provision's heading, status and opening words, and
a link to the whole thing. You find out whether you need to go there without going there.

The card is hoverable (you can move the pointer into it), dismissible with <kbd>Escape</kbd>, and
stays while you are pointing at it. On a touchscreen there is no card at all: tapping a citation
simply follows it, because a tap is not a hover and pretending otherwise is how a link becomes
unreliable.

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
    caption: — heading, status and opening words, without losing your place.
```

## Citing an exact text

A section page carries two addresses. The **citation URL** is the one you already know
(`/us/usc/t16/s45f/c/5`) — stable across release points, and what you want in a brief that means
"this provision, as it stands".

The other is a **guid**: `/us/usc/?id=id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd`. A guid pins one
provision at one release point, so it needs no `?release=` and no date. It means *this exact text,
as it stood at this exact moment*, and it will mean that permanently.

A guid is never a cross-release identity — the source regenerates them at every release point, by
design. For "this provision over time", the citation URL is the right address; for "the words I am
quoting", the guid is.

```scenario
id: guid-permalink
title: A guid resolves to one exact text with no release parameter
data: corpus
steps:
  - goto: /app/us/usc/?id=id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd
  - expect: { url: "/us/usc/t16/s45f" }
```

## Two settings

**Light or dark.** One control in the header. Light is the default at every operating-system
setting — this is a reading site, and the choice is the reader's rather than their laptop's. The
choice is kept in the browser and applied before the page paints, so moving between pages does not
flash.

```scenario
id: theme-toggle
title: Switch the site to dark
demo: true
demoOrder: 130
steps:
  - goto: /app/us/usc/t16/s45f
    caption: Light by default at every OS setting — this is a reading site.
  - click: .theme-toggle
    caption: One control in the header switches it.
  - expect: { selector: ".theme-toggle__label", contains: "Light" }
    caption: The choice is remembered, and lands before the page paints.
```

**Where links open.** Cross references and search results open in a new tab by default, so reading
a reference does not cost you the section you were in. [Settings](/app/settings) changes that to
the same tab. It is stored on your account, which means it is currently a preference you can only
set if accounts are on — see the next chapter.

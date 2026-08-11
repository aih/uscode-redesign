---
layout: ../../layouts/GuideLayout.astro
title: Reading the Code
order: 2
summary: Going to a provision by its citation, moving around it and inside it from the keyboard, and reading what the badges and notes on it mean.
covers:
  routes: ["/app/us/usc", "/us/usc"]
  adrs: [9, 10, 21, 25, 40, 43, 50, 52, 54, 55, 56, 58, 59, 60, 61, 63, 64]
---

## The address of a provision

A citation corresponds to a url path. Title 16, section 45f is `/us/usc/t16/s45f`; subsection (c)(5) of it is
`/us/usc/t16/s45f/c/5`. Chapters and subchapters work the same way — `/us/usc/t16/ch1` is a table
of contents rather than a section, served at the same kind of address.

```scenario
id: section-by-address
title: Open a section by its citation
demo: true
demoOrder: 20
steps:
  - goto: /app/us/usc/t16/s45f
    caption: The citation is the URL. This is 16 U.S.C. § 45f.
  - expect: { selector: ".doc-title", contains: "45f" }
    caption: The section, with its number and heading as the Code prints them.
```

Ask for a subsection and you get **the whole section, with that subsection highlighted in place**.

```scenario
id: provision-in-context
title: A subsection is shown inside its whole section
demo: true
demoOrder: 30
steps:
  - goto: /app/us/usc/t16/s45f/c/5
    caption: Ask for subsection (c)(5) —
  - expect: { selector: ".target", visible: true }
    caption: — and it is highlighted in place, inside the whole section.
```

### The bare citation URL

The address also works without the `/app` prefix. `/us/usc/t16/s45f` is a **citation URL**: it
redirects a browser to the reader and a program to the API, based on what the caller says it can
accept.

```scenario
id: citation-url-redirects
title: The bare citation URL leads a browser to the reader
steps:
  - goto: /us/usc/t16/s45f
  - expect: { url: "/app/us/usc/t16/s45f" }
```

From a script, the same address answers with JSON — `curl -L` follows the redirect, and
`-H 'Accept: application/json'` is what makes it land on the API rather than the reader. See
[The API](/app/guide/08-api).

## Site navigation

**The site menus.** The top of every page carries four things: **Titles**, **My Provisions**, the
search box, and **More**.

Titles opens a short list of titles and a link to all of them. More holds the rest of the site under
four headings — Reference (Release points, Downloads), Help (User guide, API docs, About), Display
(the reading-density and theme switches), and Accounts.

Both menus open over the page rather than pushing it down, and one is open at a time: opening either
closes the other. **Esc** closes the open menu and puts the keyboard back on the button that opened
it. So does clicking anywhere outside it.

On a window narrower than 1024 pixels the page carries a bar instead: **Menu**, the site's name, and
the light/dark switch, with the search box on its own row underneath. The search box is on screen
without opening anything. The foot of the page collapses behind **Site links**; the disclaimer under
the footer menu stays on screen either way.

Menu opens a sheet under the bar. It lists Titles, then My Provisions, then everything More holds at
a wider window — Reference, Help and Display — in the open, one heading after another, with the
Accounts row last. There is no second menu to open inside it.

```scenario
id: header-more-menu
title: The rest of the site is behind More
steps:
  - goto: /app/us/usc/t16/s45f
  - expect: { selector: '.navdrop--more .navdrop__panel', visible: false }
    caption: The top of the page carries Titles, My Provisions, the search box and More.
  - click: .navdrop--more > summary
    caption: More holds the release points, the guide, the API reference and the display switches.
  - expect: { selector: '.navdrop a[href="/app/releases"]', visible: true }
    caption: Release points is under Reference.
  - expect: { selector: ".navdrop__list .theme-toggle", visible: true }
    caption: The theme and reading-density switches are under Display.
```

```scenario
id: header-one-menu-at-a-time
title: Opening one menu closes the other
steps:
  - goto: /app/us/usc/t16/s45f
  - click: .navdrop--titles > summary
  - expect: { selector: ".navdrop--titles .navdrop__panel", visible: true }
    caption: Titles lists a few titles and a link to all of them.
  - click: .navdrop--more > summary
    caption: Opening More —
  - expect: { selector: ".navdrop--titles .navdrop__panel", visible: false }
    caption: — closes Titles.
  - press: Escape
  - expect: { selector: ".navdrop--more .navdrop__panel", visible: false }
    caption: Esc closes the open menu.
```

**The foot of the page** carries nine links under four headings:

- **Browse** — Titles, Release points
- **Learn** — User guide, Search guide, Keyboard shortcuts
- **Developers** — API documentation, Source XML (OLRC), Design system
- **Site** — About

They are four columns on a window 640 pixels or wider, two from 400 pixels, and one below that.
Each heading names the list beneath it, so a screen reader can move between the four groups.

```scenario
id: footer-groups
title: The site's own links are grouped at the foot of the page
steps:
  - goto: /app/us/usc/t16/s45f
    caption: Every page carries the same nine links at its foot.
  - expect: { selector: ".footnav__label", count: 4 }
    caption: Browse, Learn, Developers, Site.
  - expect: { selector: '.footnav ul[aria-labelledby="footnav-developers"]', contains: "API documentation" }
    caption: The API reference is under Developers.
```

The header menu opens over the page rather than pushing it down, so the text stays where it was.
Press the button again to close it.

```scenario
id: site-menu-mobile
title: Reach the site menu on a narrow screen
needs:
  viewport: mobile
steps:
  - goto: /app/us/usc/t16/s45f
    caption: On a phone the site links are behind one button.
  - expect: { selector: ".navtools .sitesearch__input", visible: true }
    caption: The search box has its own row under the bar and is always on screen.
  - click: .navmenu__summary
    caption: Menu opens the rest over the page.
  - expect: { selector: '.usa-nav__primary a[href="/app/provisions"]', visible: true }
    caption: Titles and My Provisions lead the sheet.
  - expect: { selector: '.navdrop a[href="/app/releases"]', visible: true }
    caption: Release points, the guide and the API reference follow, in the open.
  - expect: { selector: ".navdrop__list .density-toggle", visible: true }
    caption: The display switches are the last group.
```

The light/dark switch is on the bar itself, one tap from any page. The moon on the bar and the
**Dark** row under Display are the same setting: either one moves both, and both name the theme they
will switch to rather than the one you are in.

```scenario
id: theme-on-the-bar
title: Switch to dark from the bar
needs:
  viewport: mobile
steps:
  - goto: /app/us/usc/t16/s45f
  - click: .navbar > .theme-toggle
    caption: The moon on the bar switches the page to dark.
  - expect: { selector: ".navbar > .theme-toggle", contains: "Light" }
    caption: The switch now names the way back.
  - click: .navmenu__summary
    caption: The Display group holds the same switch.
  - expect: { selector: ".navdrop__list .theme-toggle__label", contains: "Light" }
    caption: It reads Light too — one setting, named the same way in both places.
```

**The breadcrumb** at the top of every page runs from the title down to the provision on screen:
`Title 16 › CHAPTER 1 › SUBCHAPTER VI › § 45f`. Every level above the current one is a link, and the
current one is marked as the page you are on. It carries the release point you are reading with it,
so moving up a level does not move you back to the present.

```scenario
id: breadcrumb-ends-here
title: The breadcrumb names the provision you are reading
steps:
  - goto: /app/us/usc/t16/s45f
  - expect: { selector: ".usa-breadcrumb__list-item.usa-current", contains: "45f" }
```

**The chapter rail** lists the sections around this one, in reading order, from the subdivision that
contains it. The section you are reading is marked. Beside a wide window it sits to the left of the
text; on a narrow one it is below the section.

Beside a wide window the rail stays where it is while the text scrolls. A subdivision longer than
the window scrolls within the rail itself.

The rail is drawn from the newest release point this site holds, and the text beside it is whatever
release point you asked for. When those differ the rail says so.

```scenario
id: chapter-rail
title: The sections around this one, with their status
demo: true
demoOrder: 35
steps:
  - goto: /app/us/usc/t16/s45f
    caption: Beside the section, the rest of the subchapter in reading order.
  - expect: { selector: ".rail__item--here", contains: "45f" }
    caption: The section you are reading is marked in the list.
  - expect: { selector: ".rail .usa-tag", visible: true }
    caption: Repealed and transferred sections show their status here, before you click one.
```

The other ways to move:

- The **sticky bar** at the top of a section carries previous, next and up-one-level, and stays put
  while you scroll. Each step names its neighbour — `← § 45e`, `§ 45g →` — except on a narrow
  screen, where the row has space for the arrows alone.
- **Previous / next cards** at the foot of the section show what is either side, with headings.
- The **keyboard**: <kbd>←</kbd> or <kbd>j</kbd> for the previous section, <kbd>→</kbd> or
  <kbd>k</kbd> for the next, <kbd>u</kbd> to go up a level. The full list is under
  [Keyboard shortcuts](#keyboard-shortcuts) below.

```scenario
id: neighbors-next
title: Move to the next section from the sticky bar
demo: true
demoOrder: 40
steps:
  - goto: /app/us/usc/t16/s45f
    caption: Reading order is preserved, and a chapter can be read section by section.
  - click: .sectionbar a[rel="next"]
    caption: The sticky bar carries previous, next and up-one-level.
  - expect: { selector: ".doc-title", contains: "45g" }
    caption: § 45g — the next section, whatever you were reading before.
```

```scenario
id: keyboard-previous
title: Move to the previous section from the keyboard
steps:
  - goto: /app/us/usc/t16/s45f
  - press: j
  - expect: { url: "/us/usc/t16/s45e" }
```

Repealed and omitted sections keep their place in reading order. They appear in prev/next and in
the chapter rail, with a badge saying what happened to them.

## Moving around inside a section

Above the text of a section is **In this section** — its top-level provisions with their headings,
then its source credit and its notes. Each row is a link to that block. Past about nine rows the
list scrolls inside itself.

```scenario
id: section-contents
title: Jump to the notes from the top of a section
demo: true
demoOrder: 45
steps:
  - goto: /app/us/usc/t16/s45f
    caption: Above the text, a section's own contents — its subsections, its source credit, its notes.
  - expect: { selector: ".contents__link", visible: true }
    caption: Every top-level provision, with its heading.
  - click: .contents__link[href="#section-notes"]
    caption: One click to the notes.
  - expect: { url: "#section-notes" }
    caption: The notes, at the foot of the section.
```

The section number in the **sticky bar** — `§ 45f` — is a link back to the top of the page. The bar
stays put at every width.

```scenario
id: sectionbar-top
title: Return to the top of a section from the sticky bar
steps:
  - goto: /app/us/usc/t16/s45f
  - click: .sectionbar__top
  - expect: { url: "#main" }
```

## Keyboard shortcuts

Press <kbd>?</kbd> on any page for this list. It is also **More › Help › Keyboard shortcuts** in the
navigation bar, and **Keyboard shortcuts** in the footer.

```scenario
id: shortcuts-from-the-menu
title: Open the shortcut list from the Help menu
steps:
  - goto: /app/us/usc/t16/s45f
  - click: .navdrop--more > summary
  - click: .navdrop__list [data-shortcuts-open]
  - expect: { selector: "#shortcuts", visible: true }
```

**Moving between sections**, on a section page:

| Key | |
|---|---|
| <kbd>←</kbd> or <kbd>j</kbd> | Previous section in reading order |
| <kbd>→</kbd> or <kbd>k</kbd> | Next section in reading order |
| <kbd>u</kbd> | Up to the chapter or subchapter that contains it |

**Moving inside a section**, on a section page:

| Key | |
|---|---|
| <kbd>c</kbd> | The contents list |
| <kbd>[</kbd> | Previous subsection |
| <kbd>]</kbd> | Next subsection |
| <kbd>s</kbd> | Source credit |
| <kbd>n</kbd> | Notes |

**Anywhere on the site:**

| Key | |
|---|---|
| <kbd>t</kbd> | Top of the page |
| <kbd>b</kbd> | Bottom of the page |
| <kbd>/</kbd> | Search or go to a citation |
| <kbd>?</kbd> | The shortcut list |
| <kbd>Esc</kbd> | Close the shortcut list, or a citation preview |

A key typed into any input, textarea, select or editable element is left alone, and so is any
combination held with Ctrl, Alt or ⌘. A jump inside a page takes the keyboard with it: <kbd>Tab</kbd>
continues from where you landed.

<kbd>[</kbd> and <kbd>]</kbd> step through the provision rows of the contents list, not its source
credit and notes rows. On a section with no subsections — a one-paragraph repeal, for instance —
they say so at the foot of the screen rather than doing nothing.

```scenario
id: brackets-on-a-repeal
title: Step through a section that has no subsections
steps:
  - goto: /app/us/usc/t16/s688
  - press: "]"
  - expect: { selector: "#keysay", contains: "no subsections" }
```

<kbd>t</kbd> goes to the top of the page's content, past the navigation. <kbd>b</kbd> goes to the
foot of the page, where the site's own links are.

```scenario
id: keyboard-bottom
title: Jump to the foot of the page from the keyboard
steps:
  - goto: /app/us/usc/t16/s45f
  - press: b
  - expect: { selector: "footer", inViewport: true }
```

```scenario
id: keyboard-help
title: Open the shortcut list from the keyboard
demo: true
demoOrder: 46
steps:
  - goto: /app/us/usc/t16/s45f
    caption: Press ? anywhere on the site.
  - press: "?"
    caption: The list opens over whatever you were reading.
  - expect: { selector: "#shortcuts", visible: true }
    caption: Every shortcut the reader has, on every page.
  - press: Escape
    caption: Escape closes it —
  - expect: { selector: "#shortcuts", visible: false }
    caption: — and you are back where you were.
```

```scenario
id: keyboard-notes
title: Jump to the notes from the keyboard
steps:
  - goto: /app/us/usc/t16/s45f
  - press: n
  - expect: { selector: "#section-notes", visible: true }
```

```scenario
id: keyboard-search
title: Reach the search box from the keyboard
steps:
  - goto: /app/us/usc/t16/s45f
  - press: /
  - expect: { selector: "#site-q:focus", visible: true }
```

## What the markings mean

**Status badges.** A section can be marked `repealed`, `omitted`, `transferred`, `renumbered` or
`reserved`. The badge prints whatever the source says. A status this site has not seen before keeps
the plain badge and prints its own word.

**Notes and source credit** sit at the end of the section, under a **Source** and a **Notes**
button. Each carries a caret — pointing down when the block is closed, up when it is open — and
opens and closes on a click or on <kbd>Enter</kbd>. They start open on a window wider than 640
pixels and closed below that. They come from the source XML unchanged.

Following a link to `#section-source` or `#section-notes` opens the block it names, as do the
<kbd>c</kbd> and <kbd>n</kbd> shortcuts.

```scenario
id: apparatus-toggle
title: Close and reopen the notes
demo: true
demoOrder: 47
steps:
  - goto: /app/us/usc/t16/s45f
    caption: A section, with its source credit and its notes at the end of the text.
  - scroll: .uslm-notes > summary
    caption: On a wide window both start open.
  - expect: { selector: ".uslm-notes .uslm-note", visible: true }
    caption: The amendment history, in full.
  - click: .uslm-notes > summary
    caption: The Notes button closes them, and the caret turns over.
  - expect: { selector: ".uslm-notes .uslm-note", visible: false }
    caption: The text of the section, without the apparatus around it.
  - click: .uslm-notes > summary
    caption: Pressing it again brings them back.
  - expect: { selector: ".uslm-notes .uslm-note", visible: true }
    caption: The notes, open again.
```

Dates inside a note read as part of the sentence they sit in. The source marks every date as its
own element, and the amendment histories are largely made of them — "Pub. L. 95–625 struck out
subsec. (c) effective November 10, 1978" is one sentence, and it is read as one.

```scenario
id: dates-read-inline
title: A date in a note stays in its sentence
steps:
  - goto: /app/us/usc/t16/s45f
    caption: A section whose notes carry amendment dates.
  - expect: { selector: "span.uslm-date", visible: true }
    caption: Each date is part of the running text.
```

**Occurrence 1 of 2.** Occasionally the source publishes more than one element under a single
identifier at a single release point. The site shows **every** occurrence, in the order they appear
in the file, with a note saying how many there are.

## Notes on formatting

**Section numbers use an en dash, not a hyphen.** The OLRC writes `45a–1` with U+2013 — 5,697
sections in the corpus contain one, and none contains an ASCII hyphen. The search box accepts either
and finds the right provision. A URL typed with a hyphen by hand will not resolve.

**Titles sort numerically, and `5a` is its own title.** The appendix titles (`5a`, `11a`, `18a`,
`28a`, `50a`) are separate titles with their own structure. A citation in the form `5 U.S.C. App. 3`
is understood and resolves to nothing: the OLRC publishes no section at that flat address. The site
says so on the page.

## How the text is set

Statutory text is set in Spectral, a serif. Everything written *about* the text — navigation,
breadcrumbs, badges, the release picker, search, and the editorial notes and source credit under a
section — is set in Archivo, a sans serif. Identifiers, guids and API examples use whatever
fixed-width face your system provides.

Both faces are served from this site. No font is fetched from Google Fonts or any other host.

The reading column holds a median of 67 characters per line — 62 to 71 across the tenth and
ninetieth percentiles, counted from where the browser broke the lines
(`docs/verification/measure.json`). On a screen narrower than the column, the column is as wide as
the screen; at 375 CSS px it holds 38 characters. The text is never justified and is never
hyphenated automatically.

### The subsection ladder

Each level of a provision — (a), then (1), then (A), then (i), then (I) — is indented one step
further than the level containing it, and its number hangs out to the left of the text. The numbers
at one depth line up with the text at the depth above. The step is about three characters wide, and
two below 40em. A long number such as `(xxviii)` pushes the words beside it along that line rather
than wrapping them underneath itself.

A level with no heading runs in behind its number — "(1) There is authorized to be
appropriated…" — the way the printed Code sets it. A level with a heading keeps the heading beside
the number and starts its text on the next line.

The deepest provision in the Code is seven levels down. 91.8% of sections stop at three
(`docs/verification/ladder.json`).

### The kinds of text in one column

| | How it is set |
|---|---|
| Operative text | Spectral, the reading face |
| Quoted amending text | Spectral, on a tinted panel labelled **Quoted** |
| Editorial notes | Archivo, behind a pale left rule |
| Source credit | Archivo, under a rule at the foot of the section |
| Tables | Archivo, with figures aligned in columns |

Quoted amending text is words an act is moving around rather than words in force. Most of it sits
inside an editorial note describing the amendment that made it. It keeps the reading face, on a
tinted panel under a **Quoted** label.

A table wider than the column scrolls inside its own box rather than pushing the page sideways.
The box takes keyboard focus, so <kbd>Tab</kbd> to it and the arrow keys scroll it.

## Printing

Printing a section gives you the document. The navigation, the search box, the copy column, the
chapter rail, the release picker, the **In this section** panel, the previous/next cards and the
footer are all left off the page. The notes and the source credit are printed open whatever state
they were in on screen. The page is black on white whether
or not you were reading in night mode.

Every printed sheet carries a running header with the citation, the release point, and the address
the page was printed from.

Every cross reference prints its URL after the words it sits on, in angle brackets. The printed URL
is the citation URL, carrying the release point of the page it came from.

**Limitations.** Notes print open only in browsers that support the `::details-content` selector;
in others they print in whatever state you left them, which is closed unless you opened them. A
provision longer than a page is broken across pages wherever it falls.

**Colour.** Green marks an insertion and the release currently in force. Red marks a deletion, a
repeal and an error. Amber marks the provision you asked for. Each is also spelled out in text or
shape.

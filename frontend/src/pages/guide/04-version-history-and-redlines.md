---
layout: ../../layouts/GuideLayout.astro
title: Version history and redlines
order: 4
summary: Every release point at which a section's text changed, and a readable redline between any two of them.
covers:
  routes: ["/app/versions", "/app/diff"]
  adrs: [16, 26, 66]
---

## Tracking change in the Code

Every section page links to its **version history**: one entry per distinct text, oldest first,
each showing the release point where that text first appeared and the release points it stood
unchanged through.

The Code republishes every title at every release point whether or not anything changed. The
timeline lists only the release points at which the text of this section changed.

```scenario
id: versions-timeline
title: See every release point at which a section's text changed
demo: true
demoOrder: 70
steps:
  - goto: /app/versions/us/usc/t16/s45f
    caption: "The version history: one entry per distinct text."
  - expect: { selector: "main", contains: "119-99" }
    caption: Each entry says when that text first appeared, and what it stood unchanged through.
```

## Compare with…

Every section page carries a **Compare with…** control under its heading. Opening it offers one
comparison by name — the last release point at which this section held different text — and a list
of every older release point.

The Code republishes every title at every release point whether or not anything changed, so the
release point immediately before the one you are reading usually holds exactly the same section.
The named comparison skips to the one that does not.

```scenario
id: compare-from-the-section
title: Compare a section with the last release point that changed it
steps:
  - goto: /app/us/usc/t16/s2201
  - click: .compare__summary
    caption: Compare with… opens under the section heading.
  - click: .compare__go
    caption: The offer names the last release point holding different text.
  - expect: { selector: ".diff-verdict", visible: true }
    caption: The redline between that release point and the one you were reading.
```

If you are reading a subsection rather than a whole section, the comparison keeps it: the redline
covers the whole section, and the subsection you came from is marked inside it with a line above
saying how much of the change is in it — including when the answer is none.

```scenario
id: compare-keeps-the-provision
title: Compare a subsection and see it marked in the section's redline
steps:
  - goto: /app/us/usc/t16/s2201/b/1
  - click: .compare__summary
  - click: .compare__go
  - expect: { selector: ".diff-focusnote", contains: "(b)(1)" }
    caption: The redline says which subsection it was asked about.
  - expect: { selector: "#diff-focus", visible: true }
    caption: And marks it inside the whole section.
```

## The redline

From the timeline, or from the From/To picker at the foot of it, you get a **redline** between any
two release points: removed words struck through, added words underlined, in the reading text.

The redline compares the **reading text**. A second view compares the source XML, and shows
changes to `@id` and the rest of the markup.

```scenario
id: diff-real-change
title: Compare two release points and see what the words did
demo: true
demoOrder: 80
data: corpus
steps:
  - goto: /app/diff/us/usc/t16/s45f?from=113-21&to=119-99
    caption: A redline between any two release points, in the reading text.
  - expect: { selector: "main", contains: "Comparing" }
    caption: Removed words struck through, added words underlined.
```

### Summary of changes

The line under the two release points is the result: `No changes`, or a count —
`2 lines added`, `3 lines changed, 1 line removed`.

When the words are the same and the stored XML is not, the line under the result links to the
source redline, which shows the metadata that changed — guids, whitespace, an attribute that
carries no words.

When both release points serve the same stored fragment, the note under the result names the
release point whose `@id` guids that fragment carries.

```scenario
id: diff-nothing-changed
title: An unchanged section says what the source did anyway
steps:
  - goto: /app/diff/us/usc/t16/s45f?from=119-99&to=119-102not101
  - expect: { selector: ".lede", contains: "No changes" }
  - expect: { selector: "main", contains: "Identical content is stored once" }
```

### The source redline

Under the reading redline there is a link to the same comparison at the level of the source XML,
behind `?source=1` and closed by default. The API returns the same comparison as JSON; see
[The API](/app/guide/08-api).

## Notes on redlines

**Cross-reference links are dropped inside the redline.** The comparison is over text, and a
citation that is a link in the section view is plain text here.

**A change in whitespace alone is not shown in the reading redline.** The source view shows it.

**Comparisons are rate limited.** Building one is the most expensive thing this site does, so a
burst of eight is allowed and the allowance refills at one every two seconds. Past that the page
answers `429` with a `Retry-After` header saying how many seconds to wait, and offers a link back to
the section you were comparing.

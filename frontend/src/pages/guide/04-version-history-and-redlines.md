---
layout: ../../layouts/GuideLayout.astro
title: Version history and redlines
order: 4
summary: Every release point at which a section's text changed, and a readable redline between any two of them.
covers:
  routes: ["/app/versions", "/app/diff"]
  adrs: [16, 26]
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

The textual changes are shown on the diff page. If there are non-textual metadata changes (e.g. a change in @id or @temporalId, or a change in whitespace), the page says what has been changed.

```scenario
id: diff-nothing-changed
title: An unchanged section says which kind of unchanged it is
steps:
  - goto: /app/diff/us/usc/t16/s45f?from=119-99&to=119-102not101
  - expect: { selector: "main", contains: "same stored text" }
```

### The source redline

Under the reading redline there is a link to the same comparison at the level of the source XML,
behind `?source=1` and closed by default. The API returns the same comparison as JSON; see
[The API](/app/guide/08-api).

## Notes on redlines

**Cross-reference links are dropped inside the redline.** The comparison is over text, and a
citation that is a link in the section view is plain text here.

**A change in whitespace alone is not shown in the reading redline.** The source view shows it.

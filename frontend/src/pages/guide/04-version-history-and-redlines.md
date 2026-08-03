---
layout: ../../layouts/GuideLayout.astro
title: Version history and redlines
order: 4
summary: Every release point at which a section's text changed, and a readable redline between any two of them.
covers:
  routes: ["/app/versions", "/app/diff"]
  adrs: [16, 26]
---

## When did this change?

Every section page links to its **version history**: one entry per distinct text, oldest first,
each showing the release point where that text first appeared and the release points it stood
unchanged through.

That is the useful shape. A list of all 382 release points would be true and useless — the Code
republishes every title at every release point whether or not anything changed, so most entries
would say nothing happened. What the timeline lists is the *changes*.

```scenario
id: versions-timeline
title: See every release point at which a section's text changed
demo: true
demoOrder: 70
steps:
  - goto: /app/versions/us/usc/t16/s45f
    caption: "The version history: one entry per distinct text, not one per release point."
  - expect: { selector: "main", contains: "119-99" }
    caption: Each entry says when that text first appeared, and what it stood unchanged through.
```

## What changed?

From the timeline, or from the From/To picker at the foot of it, you get a **redline** between any
two release points: removed words struck through, added words underlined, in the reading text.

The redline is of the **reading text**, not of the source XML. That is the difference between a
tool that shows you an amendment and one that shows you 51 changed attributes: the source
regenerates every `@id` guid at every release point by design, so a diff of the raw XML reports
enormous churn on a section whose words nobody touched.

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
    caption: Removed words struck through, added words underlined — the amendment, not the markup.
```

### When nothing changed, it says which kind of nothing

An empty redline is ambiguous, and the ambiguity matters. It could mean the two release points
serve the same stored text; or that the XML differs only in guids, which pin a provision to a
release point and say nothing about the law; or that it differs by more than guids — whitespace, a
`@temporalId` — none of which is a word. The page says which of the three it is rather than letting
"identical" stand for all of them.

```scenario
id: diff-nothing-changed
title: An unchanged section says which kind of unchanged it is
steps:
  - goto: /app/diff/us/usc/t16/s45f?from=119-99&to=119-102not101
  - expect: { selector: "main", contains: "same stored text" }
```

### The source redline

Under the reading redline there is a link to the same comparison at the level of the source XML,
behind `?source=1` rather than open by default — computing it is the expensive part, and most
readers want the words. The API returns the same comparison as JSON; see
[The API](/app/guide/08-api).

## Two things the redline will not show you

**Cross-reference links are dropped inside the redline.** The comparison is over text, so a
citation that is a link in the section view is plain text here.

**A change in whitespace alone is invisible**, since the redline compares displayed text and the
display does not distinguish it. The source view will show it.

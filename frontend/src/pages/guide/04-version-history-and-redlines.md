---
layout: ../../layouts/GuideLayout.astro
title: Version history and redlines
order: 4
summary: Every release point at which a section changed, which of those changes were amendments, and a readable redline between any two of them.
covers:
  routes: ["/app/versions", "/app/diff"]
  adrs: [16, 26, 66, 74, 75, 77]
---

## Tracking change in the Code

Every section page links to its **version history**, and the link says how many times the section
has been amended and over how many release points. The history lists one entry per distinct stored
text, oldest first, each showing the release point where that text first appeared and the release
points it stood unchanged through.

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

## Amendments and every recorded version

The site stores a new version of a section whenever its published XML changed. Most of those
changes are not amendments: a note edited, a source credit extended, an attribute or a whitespace
character moved by the converter that produced the file. Across the whole corpus, 7.8% of recorded
transitions changed the statutory text, 17.1% changed only the notes, and 75.1% changed neither.

The history opens on the amendments — the transitions that changed the statutory text, and the
oldest text the site holds, which is marked as such. Under the summary line there are two options:

- **Amendments (N)** — the default. N counts the amendments.
- **All recorded versions (M)** — every stored version, including notes-only and metadata-only
  changes. Its address is the same page with `?view=all`.

In the default view an entry's "Unchanged through" run covers the hidden versions after it, so the
release points it names are every release point at which the section read that way.

```scenario
id: versions-all-recorded
title: Switch between the amendments and every recorded version
steps:
  - goto: /app/versions/us/usc/t16/s2201
    caption: The history opens on the amendments.
  - click: "[data-sort='all']"
  - expect: { url: "view=all" }
    caption: All recorded versions — the notes-only and metadata-only changes as well.
  - expect: { selector: "[data-sort='text']", visible: true }
    caption: The other option is a link back.
```

## What each entry says

An entry carries the public laws OLRC's classification tables record against this section for that
change, as chips: **Pub. L. 119–102**. A chip links to the classification lookup, which leads to the
table row. Where the tables record an action other than a plain amendment — `new`, `repealed`,
`tr to` — the chip carries that word. The line above the chips says what the list is: **Amended by**
on an entry that changed the statutory text, **Public laws recorded for this change** on one that
changed a note or the markup.

A notes-only entry is attributed by the tables' note rows: where a law's provision was classified
as a note under the section and that law arrived with the change, the entry carries its chip.

Where OLRC moved a provision into or out of the section without Congress amending it, the
Editorial Classification Change Table records the move and the law that prompted it. Such an entry
reads as an editorial reclassification, its chips are led by **Editorial reclassification prompted
by**, each chip carries `ed chg`, and the move is written beside it as the table writes it:
`42:294t nt → 42:294u new`.

Where the text changed and no statute is recorded against it, the entry says so. Roughly half of
text changes are in that state: footnote markers, editorial trimming of cross references,
renumbering notices, and amendments the tables do not carry.

In the all view, a notes-only entry reads "Notes updated" and a metadata-only entry reads
"XML/metadata only".

Each entry after the first links to a redline against the release point before it. Where another
stored version is mapped inside the release points an entry arrives across, the entry says so and
offers no redline; the From/To picker at the foot of the page still reaches one.

```scenario
id: versions-law-attribution
title: See which public law made an amendment
steps:
  - goto: /app/versions/us/usc/t16/s2201
  - expect: { selector: ".timeline", contains: "Pub. L. 119–102" }
    caption: The public law the classification tables record for that amendment.
```

### Limitations

A change to whitespace alone is recorded as a metadata change, so it does not appear in the
amendments view.

The classification tables begin at the 104th Congress. An amendment older than that carries no
chip. The Editorial Classification Change Table covers the 119th Congress only.

## The From/To picker

At the foot of the version history, From and To choose any two of the section's recorded versions
and open a redline between them. The list covers every recorded version in both views, and says so
when the view on screen is showing fewer.

## Compare with…

Every section page carries a **Compare with…** control under its heading. Opening it offers one
comparison — the last release point at which this section held different statutory text — and a
list of every older release point.

The Code republishes every title at every release point whether or not anything changed, so the
release point immediately before the one you are reading usually holds exactly the same section.
The named comparison skips to the last one that read differently.

```scenario
id: compare-from-the-section
title: Compare a section with the last release point that changed it
steps:
  - goto: /app/us/usc/t16/s2201
  - click: .compare__summary
    caption: Compare with… opens under the section heading.
  - click: .compare__go
    caption: The offer names the last release point holding different statutory text.
  - expect: { selector: ".diff-verdict", visible: true }
    caption: The redline between that release point and the one you were reading.
```

If you are reading a subsection rather than a whole section, the comparison keeps it: the redline
covers the whole section, and the subsection you came from is marked inside it with a line above
saying what changed, if anything.

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

The redline uses Google's Diff-Match-Patch algorithm to compare the **reading text**. A second view compares the source XML, and shows
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
source redline, which shows the metadata that changed — `guid`s, whitespace, an attribute that
carries no words.

When both release points serve the same stored fragment, the note under the result names the
release point whose `@id` `guid`s that fragment carries.

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

**A change in whitespace alone is not shown in the reading redline.** The source view does show it.

**Comparisons are rate limited.** Building one is the most compute-intensive process on the site, so a
burst of twenty is allowed and the allowance refills at one a second. Past that the page
answers `429` with a `Retry-After` header saying how many seconds to wait, and offers a link back to
the section you were comparing. Future versions of the site may offload diff functionality to the browser.

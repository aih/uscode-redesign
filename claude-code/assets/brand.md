# Brand proposal — reasoning and values

There is no brand today; the reader wears USWDS defaults. USWDS is the right chassis for a site
about federal law and the wrong thing to look identical to — it reads as "an agency site", and this
is not one. The proposal keeps the chassis and changes the surface.

## Positioning
A citation is an address. That is the site's whole idea, and the design should look like precision
instruments rather than like a government portal: quiet, dense where density helps, generous where
reading happens.

## Typeface
- **Spectral** — statute text, notes, source credit. A screen-first serif with a large x-height and
  a genuine italic; holds up at 320px and in print, which is where drafters read.
- **Archivo** — interface: chrome, breadcrumbs, timeline, badges, search, tables of contents. A
  grotesque with a condensed family available, which the release-point labels
  (`119-102not101`) will need.
- One monospace (system stack) for identifiers, guids and API examples.
- Both self-hosted as subset variable WOFF2. No font CDN.

Why not keep USWDS's Public Sans / Merriweather: Public Sans is the federal voice, deliberately.
Borrowing it makes a prototype look like an official publication, which is a claim this site should
not make.

## Colour (oklch, one chroma, hue varied)
| Role | Value | Use |
| --- | --- | --- |
| Ink | `oklch(0.22 0.015 265)` | body text, warm-cool neutral rather than pure black |
| Paper | `oklch(0.985 0.004 85)` | page background, a trace warm |
| Primary | `oklch(0.45 0.13 265)` | links, focus, active nav — deep indigo |
| Primary hover | `oklch(0.36 0.13 265)` | |
| Secondary | `oklch(0.45 0.13 155)` | reserved for **version semantics only**: current release, timeline markers, insertions |
| Deletion | `oklch(0.45 0.13 25)` | redline deletions, error states |
| Muted | `oklch(0.55 0.01 265)` | metadata, source credit |
| Rule | `oklch(0.90 0.008 265)` | hairlines, TOC dividers |

The discipline that matters more than the hues: **green and red mean "changed", nothing else.** No
green buttons, no red destructive styling. If a colour can mean two things on a page about
amendments, it means neither. And per A5/A7, colour is never the only carrier — every insertion,
deletion, and status also has text or shape.

Dark theme: same hues, lightness inverted around the same chroma; re-run the contrast table rather
than trusting the transform.

## Reading
- Measure 62–70 characters. Reading size 1.125rem baseline, 1.6 line height for statute text.
- The subsection ladder is one indentation scale with hanging numbers, degrading at 320px.
- `text-wrap: pretty` on prose; never justified.

## What stays USWDS
Grid, spacing scale, form controls, focus mechanics, banner/footer structure, alert components. All
overrides are token-level plus a small set of project components (breadcrumb-with-release, TOC
rail, timeline, redline, status badge, copy control) documented on `/app/design`.

## Wordmark
Set in Archivo, letter-spaced small caps: **U.S. Code** with **linkedlegislation** beneath at a
smaller size, plus one mark — a bracketed section sign, `[§]`, drawn from the type rather than
illustrated. No logo illustration; this is a typographic brand. If a drawn mark is wanted, that is
a job for a designer working in vector, not something to generate.

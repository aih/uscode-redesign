# ADR-0054 — Typography for statutory text

- **Status:** Accepted
- **Date:** 2026-08-05
- **Context:** Session 31, workstream C task C3, following [ADR-0052](0052-a-brand-layer-over-uswds-expressed-only-as-tokens.md) and [ADR-0053](0053-a-living-style-guide-at-app-design.md)
- **Depends on:** [ADR-0015](0015-one-origin-two-services-renderer-in-the-frontend.md) (the USLM renderer), [ADR-0040](0040-inline-or-block-is-decided-per-occurrence.md) (inline or block, per occurrence), [ADR-0005](0005-what-counts-as-a-section.md) (a section inside `<quotedContent>` is not a section), [ADR-0046](0046-per-route-javascript-byte-budget.md) (the byte budget the density island spends)

## Context

ADR-0052 chose the faces and the measure. It did not say how the text is set inside the column,
and the reading column is the product.

Four things were wrong or missing, and the first is the largest.

**The subsection ladder did not exist.** `--indent-step` was declared, documented as the lever for
provision depth, and reached only `[class*="indent"]` — the source's own `indentN` classes, which
occur inside notes and tables. No rule indented a `<subsection>`, a `<paragraph>` or a `<clause>`.
On every section page in the corpus `(a)`, `(1)`, `(A)` and `(i)` sat flush at one left edge, and
the only way to tell a clause from the subsection containing it was to read both. The same selector
gave one step of indent to all 28,142 occurrences of `indent0`, which means no indent, and to
`indentUp0`, `indentDown2` and `indentTo54pts`, which mean three other things.

**The five kinds of text in the column were three.** Operative text, quoted amending text, editorial
notes, the source credit and the source's tables all shared the reading face. A block quotation and
an editorial note were the same 4px `--rule` down the left edge and nothing else, so the words an
act *inserts* and the OLRC's prose *about* the insertion were distinguishable only by reading them.

**Tables were designed for a schema the parser does not read yet.** `Uslm2Parser` has no table
handling; USLM 2.x carries 781 tables in `usc49.xml` alone, in the XHTML namespace, 766 of them with
a `<caption>` — and `caption` was in no vocabulary in `uslm.ts`, so it fell through to the `<div>`
fallback. A `<div>` is not valid inside a `<table>`: the browser hoists it out, unstyled, above the
table it titles.

**Nothing was designed for paper.** Drafters print. A printed page carried the navigation, the
search box, the copy column, the footer, the reader's `/app` URLs as bare link text, and no
statement anywhere of which release point the text was read at — a page of statutory text of unknown
vintage, which is the failure this whole project exists to prevent.

## Decision

### 1. The measure is a multiple of the reading size, and the text is never justified

`--measure` becomes `calc(40 * var(--reading-size))`. At the default size that is 42rem to the
pixel — the same column ADR-0052 measured — and it stays the same *measure* when the reading size
moves, which a fixed 42rem would not: a smaller face in an unchanged column is more characters a
line, straight out of the 62–70 the brand asks for. `make measure` counts both densities.

`text-align: start`, `text-wrap: pretty`, `hyphens: manual`. Justification is refused: uneven word
spacing in a 68-character column carrying `notwithstanding` and `§ 1531(a)(2)(A)` opens rivers. The
source does write `text-align:justify` inline, 1,948 times in `usc16.xml` and never in the USLM 2.x
samples — every one on a `<td>` or the `<p>` inside it, none on statutory prose. Those keep winning:
an inline style outranks the stylesheet, and a leader table is the one place justification is doing
a job.

### 2. One indentation scale, with hanging numbers

Every level below the section root carries `prov`, emitted by `uslm.ts` from its own `LEVEL_TAGS`,
so the stylesheet never enumerates USLM element names and there is no second list to fall out of
step (architecture rule 5). Each `.prov` spends one `--indent-step` of `padding-left`; the nesting
does the arithmetic rather than a depth counter. The `<num>` is pulled back by exactly that step, so
the numbers at one depth align with the text at the depth above.

The step is in `em` rather than `rem`, so it is a multiple of the text it indents and follows the
density control without being restated. `em` rather than `ch`, and that is not cosmetic: `ch` is the
width of a `0` in the font of the element using it, and `.uslm-num` is bold — 3ch of Spectral Bold
is 3px wider than 3ch of Spectral, so the number's negative margin overshot its parent's padding and
every designator hung 3px into the column above it. `em` is font-*size* relative and weight does not
change font size. Measured against Spectral at 16.8px: `(a)` is 0.99em, `(1)` 1.00em, `(A)` 1.21em,
`(i)` 0.80em, `(viii)` 1.90em, `(xxviii)` 2.89em. `scripts/ladder.py` measures the rest into
`docs/verification/ladder.json` — the ladder reaches depth 7 at `/us/usc/t16/s1391`, 11 of 11,512
sections get there, 91.8% stop at depth 3, and the median designator is three characters at every
depth.

**1.5em, and 1em below 40em.** That is the degradation the small screen asks for. `min-width` and not
`width` on the number: a designator wider than the step pushes the words beside it along that one
line rather than wrapping them underneath itself, which is the failure a hanging indent exists to
prevent. At 320 CSS px the seven-deep clause spends 118px of a 288px column and keeps about 20
characters a line; depth 3 spends 50px and keeps 28.

The body of an **unheaded** level runs in behind its number — "(1) There is authorized…", the way
the printed Code sets it. A level *with* a `<heading>` does not: running that in needs a separator
between the heading and the first word, USLM 1.x writes none, and inventing an em dash the source
does not have would be this page adding punctuation to a statute.

The source's own `indentN` classes describe the same indentation from the other side —
`<subsection class="indent2 firstIndent-2">` is OLRC's rendering of the printed edition's leading.
One scale means one of them wins on a level element, and it is the structural one: `.prov` zeroes
both `margin-left` and `text-indent`. Left to compose, § 45f's subsections started 78px in rather
than 0, its paragraphs 129px, and two sibling paragraphs at the same depth sat 25px apart because
the source wrote `indent1` on one and `indent0` on the other. Outside a level — inside notes and
tables, where the source's scale is the only one there is — `indent0` through `indent7` spend N
steps, `indent0` spends none, and `firstIndent-N` is the negative `text-indent` it describes.

### 3. Five kinds of text, told apart by the face first

**The law is set in Spectral and everything written about the law is set in Archivo** — the same
division ADR-0052 drew between the text and the interface, applied inside the reading column.

| | Face | Treatment |
|---|---|---|
| Operative text | Spectral | `--ink`, full measure |
| Quoted amending text | Spectral | `<blockquote>`, tinted panel, `--edge` rule, "Quoted" down the edge |
| Editorial notes | Archivo | `--muted`, pale left rule |
| Source credit | Archivo | `--muted`, above a rule |
| Tables | Archivo | tabular figures, caption, focusable scroll region |

Quoted amending text keeps the reading face because it *is* statutory text; a drafter reads it as
closely as the operative text. It is a `<blockquote>` rather than a `<div>` so the boundary is
carried by the markup as well as by the paint. Most quotations sit inside an editorial note, which
is why the rule restates the face and the size: without that, the words an act inserts inherit the
face reserved for writing about the law. A `<section>` inside one is not a section (ADR-0005) and
renders inside the quotation that owns it, with its own number and heading.

`quotedContent` is a block quotation 875 times and a phrase inside a sentence 2,701 times
(ADR-0040); only the block form gets any of this. An inline one inherits its sentence entirely —
box, face, size and colour.

Tables arrive inside `.uslm-tablewrap`, which is the scrollable box and carries `role="region"` and
`tabindex="0"`, named from the table's own `<caption>`. Two scrollable regions with no keyboard
route into them are already on `docs/a11y/known-violations.json`; this is not going to be a third.

### 4. A print stylesheet

A running header repeats in the top margin of every sheet — `PrintHeader.astro`, `position: fixed`
at a negative `top`, which is how paged media repeats a box across pages. It carries the citation,
the release point, and the host and path the page was printed from. The host comes from the
request's own `Host` header rather than a configured canonical origin, because there is no
configured canonical origin and the URL worth printing is the one the reader used.

Notes and the source credit stay, forced open through `::details-content`. The chrome goes:
navigation, search, the rail, the copy column, the release picker, the footer. The release *facts*
stay — `ReleaseContext` is a statement, not a control. The theme does not travel: the print block
forces black on white, because a dark theme sent to a printer is either a black page or, once the
printer drops the background, the statute at 2:1.

Every cross reference prints its URL after the words it sits on, in angle brackets.
`data-print-url` carries `citationHref` — the bare citation URL with the release point — rather than
`attr(href)`, which would print the reader's own `/app` path.

### 5. Reading density, as a token switch

`comfortable` (default) and `compact`, on `<html data-density>`, in `localStorage` under
`usc-density`, stamped by the same pre-paint bootstrap that stamps the theme. Not a cookie, for
ADR-0018's reason: a density cookie would put `Vary: Cookie` on statutory text that is identical for
everybody.

Compact moves three tokens and nothing else — `--reading-size` 1.05rem → 1rem,
`--reading-leading` 1.6 → 1.4, `--reading-gap` 0.75rem → 0.4rem. `--measure` and `--indent-step`
follow from those, so a compact page is the same 62–70 characters a line in a narrower column
rather than a longer line in the same one. It is deliberately not a smaller *face*: compact is for a
reader comparing two versions of a long section on one screen, and the way to give them that is to
spend less on the space between lines.

The control's label names the destination, so it alternates between "Compact" and "Comfortable" —
two widths in a flex row. The label carries a reserved `min-width`, or the theme toggle beside it
moves on every click.

## Consequences

Measured, and re-checkable:

- `uv run python scripts/ladder.py` → `docs/verification/ladder.json`. Depth, designator widths and
  the source's indent classes, from the committed samples. No database, no network.
- `make measure` → `docs/verification/measure.json`, now at both densities, holding the median
  between 62 and 70 where the column is at its maximum.
- `frontend/tests/e2e/typography.spec.ts` asserts the rendered ladder against the depth
  `ladder.json` reports, the density round trip, and the print treatment.

### Costs accepted

**The density control costs a row on a phone.** At 375px it wraps `.navtools` to a fourth line and
the header grows 56px, measured. `--sticky-h` is unaffected at every width — 0px of cost at 700,
1024 and 1280, and below 40em the header is not sticky at all — so no anchor jump changes. The
reader scrolls past the header once.

**~950 bytes of inline script on every route**, and 456 more on `/app/design` for the density
readout. Every ceiling in `docs/js-budgets.json` rises. That is what ADR-0046 exists to surface.

**Notes print open only where `::details-content` is supported.** A browser without it prints
whatever state the `<details>` was in, which is closed unless the reader opened it. This is the same
fallback the ≥40em rule already accepts, and it is now load-bearing for a printed page rather than
for a convenience.

**The running header is `position: fixed` in a negative top margin.** That is the only mechanism
browsers give for a repeating running head — `@page` margin boxes are specified and unimplemented.
It depends on `@page { margin-top: 22mm }` staying larger than the header, and nothing asserts the
relationship.

**A headed level still breaks its line after the heading.** `(a) In general` then the text below,
where the printed Code runs the two together. Refused above, for the missing separator.

**Every table takes a tab stop**, whether it scrolls or not. CSS cannot make `tabindex` conditional
on overflow, and the alternative is a scroll region a keyboard cannot reach. Tables are rare — 822
across the committed samples — but a section carrying several now costs several stops, the same
shape of cost ADR-0033 records for the copy column.

**The source's `indentUp0`, `indentDown1`, `indentDown2`, `indentTo54pts`, `indentTo65ptsHang` and
`indent0And43pts` classes are now styled by nothing.** They were each getting exactly one step from
the substring selector, which was wrong for all of them; naming the levels is correct and leaves
these unstyled rather than wrongly styled. Together they are 8,733 occurrences across the samples,
all inside notes and tables. Reading them properly is its own task.

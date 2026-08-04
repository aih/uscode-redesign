# Workstream C — Brand and design system

Constraint that decides everything here: the reader is **USWDS** (ADR-0011/0015), server-rendered,
with a handful of islands. Do **not** replace USWDS, and do not introduce a second CSS framework or
a utility-class layer. All visual change lands as **design-token overrides plus a small number of
project components built from USWDS primitives.** That is what keeps speed (no new runtime) and
extensibility (the next page inherits the system for free).

---

## C1 — Adopt a brand, as tokens

Read `assets/brand.md` in this package for the proposal and the reasoning. In short: a serif for
statute text (Spectral), a grotesque for interface (Archivo), an indigo primary, a forest-green
secondary reserved for version/currency semantics, warm neutral greys, and a fixed measure for
reading.

Steps:
1. **Audit before overriding.** Find the USWDS theme entry point in `frontend/src/styles/`
   (`_uswds-theme*.scss` or the project's equivalent) and list every token the project already
   sets. Report which of the proposal's changes are token changes and which would need component
   overrides — then only do the token ones in this task.
2. Land `assets/_uswds-theme-overrides.scss` adapted to your installed USWDS version (verify every
   token name against `node_modules/@uswds/uswds/packages/uswds-core/_index.scss`; the names in the
   file are written for USWDS 3.x and will drift).
3. Self-host both fonts as variable WOFF2, subset to Latin, `font-display: swap`, preloaded — no
   third-party font CDN. A statute reader must render text before a network round trip to someone
   else's server, and the CSP (ADR-0030) should not have to allow a font origin.
4. Verify: `make shots` at 320/375/1280 shows no sideways scroll; the contrast table from A7
   regenerates clean in both themes; the JS byte budget from B3 is unchanged (this task adds no
   JavaScript).

ADR: "A brand layer over USWDS, expressed only as tokens." Record the cost — a serif at
`--reading` size increases line height and therefore scroll length on long sections; and two
self-hosted variable fonts add ~90–120 KB to the critical path, which the byte budget must absorb.

---

## C2 — A living style guide at `/app/design`

One page, generated from the same tokens, showing: the type scale in both faces with the reading
measure; the palette with computed contrast ratios; focus states; the status badge set
(`repealed`/`omitted`/`transferred`/`reserved`, and remember status is **not a closed set** —
gotcha 13, USLM 2.x adds `renumbered` — so the badge component must render an unknown status
legibly rather than throwing); breadcrumb; TOC rail; timeline; redline; copy control; search result
row; and every message state (zero results, 429, served-from, appendix explanation).

This page is the regression surface for the design system: `make shots` covers it, axe scans it
(A1), and the guide ratchet requires a chapter to account for it. Any component that does not
appear here is not part of the system.

---

## C3 — Statute typography spec

The one place to be genuinely careful, since it is the product.

- Measure 62–70 characters at the default size; `text-wrap: pretty`; no justification.
- The subsection ladder — (a) (1) (A) (i) — expressed as one indentation scale with hanging
  numbers, so a deeply nested clause is scannable and still readable at 320px, where the ladder
  must degrade to a smaller step rather than wrapping into the number.
- Distinguish, visually and semantically: operative text, quoted amending text
  (`<quotedContent>` — and remember it is *not* a section, ADR-0005), editorial notes, source
  credit, and the tables USLM 2.x carries (`Uslm2Parser` has no table handling yet — the design
  needs to accommodate them before the parser lands).
- A print stylesheet: the citation and release point in the running header, notes retained, chrome
  gone, URLs of `<ref>`s printed. Drafters print.
- Optional reading-density control (comfortable / compact) as a token switch, persisted like the
  theme, no layout shift.

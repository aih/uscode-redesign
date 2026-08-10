# Menu refinement — implementation spec for aih/uscode-redesign

Final proposal: section 2a of `Menu Proposal.dc.html`. Grounded in the repo: brand tokens from
`claude-code/assets/brand.md`, chrome inventory from `docs/ia-map.md`, conventions from
`claude-code/00-CONVENTIONS.md`. Uses only existing tokens/fonts — no new colors or typefaces.

## The change in one paragraph

SiteHeader goes from 11 interactive items (Titles, Release points, My Provisions, User guide,
API docs, About, Downloads-SOON, Accounts-SOON, Compact, Dark, search+Go) to 4: **Titles**,
**My Provisions**, the **one search box** (ADR-0023, widened, now also a ⌘K palette), and a
**More** menu absorbing the rest — Release points and Downloads under REFERENCE, User guide /
API docs / About under HELP, Compact + Dark as labeled switches under DISPLAY, Accounts (SOON)
last (this row becomes the AuthNav slot when ACCOUNTS_ENABLED flips). The contextbar's
ReleasePicker (ADR-0056) is untouched — the header's "Release points" link was only the archive
page. SiteFooter keeps all 9 links but groups them: BROWSE / LEARN / DEVELOPERS / SITE, with the
attribution band verbatim.

## Header spec (≥64em)

- One row, 60px. Order: wordmark · Titles ▾ · My Provisions · search (flex, max-width 620px) ·
  spacer · More ▾
- Titles dropdown: 5–7 frequent titles + "All 54 titles →" to `/app/`
- Search placeholder: "Search, or go to a citation — 11 usc 523(a)(1)"; keep the Go button and
  the `/app/goto` form action (no-JS path unchanged). Move the current "(i)" info-panel content
  into the palette's footer hint or keep the info toggle inside the input's right edge.
- More menu: 270px panel; group labels 10.5px/600/letter-spacing 0.09em/muted; items 14px,
  padding 8px 10px; toggles are real controls (the same handlers Compact/Dark use today), so
  display settings change without navigation.
- One disclosure open at a time; Esc and outside-click close; `aria-expanded` on triggers. Keep
  the existing `<details>` mechanics if simpler (ADR-0058 pattern) — visual spec is the same.

## Command palette (progressive enhancement, ADR-0023 kept)

- ⌘K / Ctrl+K anywhere, or focusing the search box with JS on, opens a 620px dialog over the page.
- Row groups: CITATION (client parse via `frontend/src/lib/cite.ts` / `citationforms.ts` — same
  result `/app/goto` would give), then full-text search row, then ACTIONS: "Compare with previous
  release point…" (the B5 entry point), "Add to My Provisions", "Keyboard shortcuts (?)" opening
  ShortcutsDialog.
- `<dialog>`, focus trapped, Esc closes, focus returns to the box. Register ⌘K in
  `frontend/src/lib/shortcuts.ts` next to the existing bindings; without JS nothing changes.
- It is an island — respect `docs/js-budgets.json`.

## Footer spec

Four columns (stack to two at 40em, one at 25em):
- BROWSE: Titles · Release points
- LEARN: User guide · Search guide · Keyboard shortcuts (still the guide-chapter no-script fallback)
- DEVELOPERS: API documentation · Source XML (OLRC) ↗ · Design system
- SITE: About · Accounts (SOON)
Attribution band and source-commit line unchanged, verbatim.

## Mobile (<64em)

Bar 52px: Menu (existing `<details>` disclosure, opens over the page per ADR-0058) · wordmark ·
theme toggle. Search row full-width below the bar, always visible (search + citation jump stay
one tap). Menu sheet order: Titles, My Provisions, divider, Release points, User guide, API docs,
About, Downloads (SOON), divider, Compact/Dark switches. Hit targets ≥44px.

## Tokens (all existing — brand.md)

Ink `oklch(0.22 0.015 265)` · Paper `oklch(0.985 0.004 85)` · Primary `oklch(0.45 0.13 265)` ·
Muted `oklch(0.55 0.01 265)` · Rule `oklch(0.90 0.008 265)` · current-release dot
`oklch(0.45 0.13 155)` (version semantics — the one permitted green). Archivo for chrome,
Spectral for statute text, system mono for citations in the palette input. Inputs/buttons keep
USWDS geometry (square corners, 2px focus ring); menu panels radius 4px.

## Claude Code prompts

Paste `claude-code/00-CONVENTIONS.md` above each. One task per session, in order. Each needs its
ADR, guide-chapter update with a ```scenario``` block, and BUILDLOG entry per the conventions.

**B7 — Header consolidation:**
> Task B7. Consolidate SiteHeader per docs/menu-refinement-spec.md (Header spec). Top level
> becomes: wordmark, Titles dropdown (frequent titles + "All 54 titles →"), My Provisions, the
> one search box widened to max 620px sharing the row, and a "More" menu absorbing Release
> points, Downloads (SOON), User guide, API docs, About, plus Compact and Dark as labeled
> switches under a DISPLAY group and an Accounts (SOON) row that becomes the AuthNav slot when
> ACCOUNTS_ENABLED is true. No route changes; every href still goes through
> frontend/src/lib/url.ts. Do not touch the contextbar or ReleasePicker (ADR-0056). One
> disclosure open at a time, Esc/outside-click close, aria-expanded; keep the ADR-0058 details
> pattern if it fits. Update the a11y route matrix if header landmarks changed, write the ADR
> (note the discoverability cost of moving five links behind More), update guide chapter 01/02
> scenarios, all three suites green.

**B8 — Footer grouping:**
> Task B8. Regroup SiteFooter per docs/menu-refinement-spec.md (Footer spec): BROWSE / LEARN /
> DEVELOPERS / SITE columns, same 9 links, attribution band verbatim, columns stack at 40em/25em.
> Keyboard shortcuts stays the no-script fallback to guide chapter 02 with the KeyboardNav
> intercept. Verify with the ia-map that no route loses its only footer inbound link.

**B9 — Mobile chrome:**
> Task B9. Apply the Mobile section of docs/menu-refinement-spec.md below 64em: 52px bar (Menu
> disclosure, wordmark, theme toggle), always-visible search row beneath, menu sheet ordered
> Titles / My Provisions / divider / reference+help links / divider / Compact+Dark switches. Hit
> targets ≥44px. Mind the two recorded USWDS traps: small-width .usa-nav is a centred flex
> column, and box-sizing:inherit misses pseudo-elements (see BUILDLOG ~L1863). Re-run the
> contrast checks in dark for the new menu surfaces.

**B10 — Command palette:**
> Task B10. Add the ⌘K palette per docs/menu-refinement-spec.md (Command palette): progressive
> enhancement of the one search box (ADR-0023 unchanged — form still posts to /app/goto), citation
> parse client-side via lib/cite.ts, actions rows including "Compare with previous release point…"
> as the B5 entry point and a ShortcutsDialog opener. Register ⌘K in lib/shortcuts.ts; native
> <dialog>; focus trap and restore. It is an island: stay inside docs/js-budgets.json, and add
> the per-route budget assertion if the palette pushes a route over. Guide chapter 05 gets the
> scenario; e2e covers open-with-keyboard, citation jump, Esc-restore-focus.

Suggested landing spot for this file in the repo: `docs/menu-refinement-spec.md` (the prompts
reference it there).

# Workstream A — Accessibility to WCAG 2.1 AA

Target: **WCAG 2.1 Level AA** across the reader (`/app/*`), the guide, and the API docs pages.
Section 508 conformance follows from 2.1 AA plus the published statement in A10.

Do **A1 before anything else.** Every later task in this file cites findings by rule id, and
without the harness you will be guessing at which of them are real on your build.

---

## A1 — Build the accessibility harness and make it a CI gate

Add automated accessibility scanning to the existing Playwright suite. No new test runner.

- Install `@axe-core/playwright`. Add `frontend/tests/e2e/a11y.spec.ts` (or wherever
  `make test-e2e` already looks) that iterates the route matrix in
  `docs/a11y/routes.json` — seed it from the `a11y-routes.json` shipped alongside this prompt,
  then reconcile it against the real route list (the guide ratchet's `covers.routes` is the
  authoritative inventory; use it).
- For each route, run axe with tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa` at **three
  viewports**: 320×768, 375×812, 1280×900. Also run each route in **both themes** (ADR-0027) and
  once with `forced-colors: active`.
- Scan interactive states as well as initial load: search box with results, a hover/focus preview
  open (ADR-0024), the version timeline expanded, the redline showing a diff, the copy control
  active (ADR-0033), the theme toggle after toggling.
- Write results to `docs/verification/a11y.json` — per route: violation id, impact, node count,
  first target selector. Commit it. This is the baseline artifact.
- **Ratchet, not a cliff:** the test fails on any *new* violation id/route pair not present in a
  committed `docs/a11y/known-violations.json`, and fails on any `critical`/`serious` violation
  regardless. Every entry in the known-violations file carries an owner task id from this file and
  a one-line reason. Empty by the end of Phase 2.
- Add `make test-a11y` that runs just this spec, and wire the spec into `make test-e2e` so CI
  already runs it.
- Extend `make shots` to also capture **320px** and **1280px at 200% zoom**, keeping its existing
  "fails if the page scrolls sideways" assertion. That covers 1.4.10 Reflow and 1.4.4 mechanically.

Write ADR-0039 "Accessibility is a ratchet in the browser suite" recording: why axe-in-Playwright
rather than pa11y-ci or a Lighthouse budget (one browser suite, one set of fixtures, states are
reachable); what axe cannot see (the manual protocol in A9); and the cost — axe adds runtime to
every push.

Deliverables: the spec, `docs/a11y/routes.json`, `docs/a11y/known-violations.json`,
`docs/verification/a11y.json`, ADR-0039, guide chapter mention, BUILDLOG entry.

---

## A2 — Fix `<date>` rendering (recorded debt, and it is an accessibility bug)

`CLAUDE.md` records: *"USLM `<date>` renders as a block, so dates break mid-sentence throughout
the notes — one entry in `uslm.ts`'s inline set, left out of a scoped refresh."*

Add `date` to the inline element set in `frontend/src/lib/uslm.ts`. Then audit the **whole**
inline/block partition against the USLM element vocabulary rather than fixing one entry: any
element that occurs inside running prose (`ref`, `term`, `quote`, `date`, `inline`, and whatever
else the schemas emit) must not be a block. Add a Vitest case per element asserting inline
rendering, driven by a table so the next omission is a one-line addition.

Why this is 1.3.2 and not cosmetics: a block-level date reorders the reading sequence a screen
reader announces, mid-sentence, in the editorial notes — which is exactly where a drafter is
reading for amendment history.

Verify: `make test-web`; a scenario block in the notes chapter of the guide showing a date reading
inline; `make shots` diff.

---

## A3 — Reduce the copy control's keyboard cost, and give it a text fallback

Two recorded costs, one task (ADR-0033, BUILDLOG 034):

- *"The copy column adds ~100 tab stops to a long section."* On 2.4.3 and 2.1.1 that is
  technically conformant and practically unusable: a keyboard or screen-reader user must traverse
  a hundred controls to reach the next section.
- *"Link mode has no plain-text fallback"* — if the `ClipboardItem` write throws (older Firefox,
  plain HTTP on a non-localhost host) the user is told "Could not copy" and gets nothing.

Do:
1. Make the copy column **one** tab stop per section with a roving `tabindex` inside it (ARIA APG
   toolbar pattern), arrow keys moving between provision-level copy targets, or — if the column's
   per-provision affordance is worth keeping visually — collapse to a single "Copy…" control in
   the section header that opens a menu offering *this provision / this section / citation / link*.
   Prefer whichever survives the redline and timeline islands without new state.
2. Announce results in a polite live region ("Copied § 45f(c)(5) — 1,204 characters"), not a
   transient tooltip.
3. Clipboard fallback chain: `ClipboardItem` (rich) → `writeText` (plain) → a focusable
   `<textarea>` pre-selected with the text and an instruction. Never a dead end.
4. Record in the ADR what the copied text still omits (notes, `sourceCredit`) and either fix it or
   say so in the UI — ADR-0034's rule applies to omissions, not just switched-off features.

Verify: an e2e test counting tab stops between two section headings on Title 16 § 1801 (the densest
CI fixture) — assert it is under 10; an e2e test forcing `ClipboardItem` to throw and asserting
text still lands; axe clean.

---

## A4 — Landmarks, headings, skip links, focus order under sticky chrome

Audit every reader template for:
- one `<main>`, a `<nav>` per navigation region each with an accessible name, `<header>`/`<footer>`
  used once; the TOC rail and the version timeline named, not anonymous `div`s;
- heading order with no skipped levels — the statute hierarchy (title → chapter → subchapter →
  section → subsection) must map onto `h1`–`h6` monotonically, with the *section* as `h1` on a
  section page;
- a skip link to `#main` that is the first tab stop and becomes visible on focus;
- `:focus-visible` on every interactive element at ≥3:1 against both its own background and the
  adjacent one (1.4.11), in both themes;
- `scroll-margin-top` equal to the sticky chrome height so a focused or hash-targeted provision is
  never underneath it — there are existing e2e tests for sticky geometry; extend them to *focus*
  arriving via keyboard, not just hash navigation;
- landmark and heading assertions as Vitest tests on rendered output, so this cannot regress
  silently.

---

## A5 — Timeline and redline: not by colour alone, and announced

The version timeline and the reading-text redline (ADR-0026) are the site's distinguishing
features and they are the ones most likely to fail 1.4.1.

- Insertions and deletions must carry `<ins>`/`<del>` semantics **and** a non-colour cue
  (underline / strike-through, and a leading "added"/"removed" in a visually-hidden span so the
  announcement is unambiguous).
- Non-text contrast for timeline markers, the current-release indicator, and the change bars ≥3:1
  (1.4.11).
- The redline needs a text summary before the text: "3 insertions, 1 deletion between 119-99 and
  119-102not101", in a live region when the compared releases change.
- Timeline is a real widget: keyboard-operable (arrow keys between release points, Enter to load),
  `aria-current` on the release being read, accessible names that include the currency date and the
  `not` exception (gotcha 5 — "not fully current through 07/12/2026").
- ADR-0026's named costs — the redline *drops `<ref>` links* and *cannot see a whitespace-only
  change*. Dropping links from redlined text is a content-loss issue as much as an a11y one:
  either preserve `<ref>` through the redline, or state it in the UI where the redline renders.
  Decide in an ADR amendment; do not leave it only in `CLAUDE.md`.

---

## A6 — Hover previews: keyboard and touch equivalence

ADR-0024's previews already have e2e tests for WCAG 1.4.13's three clauses (dismissable, hoverable,
persistent). Close the rest:
- focus opens the same preview hover does, Escape dismisses without moving the reading position,
  and the trigger keeps a discoverable name ("preview 16 U.S.C. § 1801");
- the preview content is reachable in the tab order while open and returns focus to the trigger on
  close;
- on touch, previews must not intercept the tap that follows the link — a tap opens the target;
- the preview endpoint is unauthenticated and fans out per hovered citation (rate-limited in
  `frontend/src/middleware.ts`, ADR-0029). A 429 must degrade to "preview unavailable — open the
  citation", not a silent empty box.

---

## A7 — Contrast and colour audit in both themes, plus forced-colors

For every token pair the design system introduces (C1) and every one it inherits from USWDS:
- text ≥4.5:1, large text ≥3:1, UI components and focus rings ≥3:1, in light **and** dark;
- status badges (`repealed`, `omitted`, `transferred`, `reserved`) never encode status by colour
  alone — badge text always present, and a shape or icon so a monochrome print still reads;
- `forced-colors: active` support: `currentColor` for icon strokes, `forced-color-adjust` only
  where genuinely required, no meaning carried by `background-image`;
- honour `prefers-color-scheme` on first visit while keeping ADR-0027's light default explicit and
  the user's choice sticky, and honour `prefers-reduced-motion` for every transition in the sticky
  chrome and timeline.
- Commit the computed contrast table to `docs/verification/contrast.json`, generated by a script
  that reads the token file — not measured by hand.

---

## A8 — Search, forms, status messaging

- Every input has a programmatic label; the one citation-and-search box (ADR-0023) needs its dual
  purpose in its accessible description, not only in placeholder text.
- Result counts, "searched release X", zero-result states and 429s announce via
  `role="status"` / `aria-live="polite"`. A zero-result state must say *why* it is zero — search is
  strict by default (ADR-0031) and that is the most likely reason — and offer the loosening
  operator that would fix this query, linking `/app/search/syntax`.
- Error identification (3.3.1) and labels/instructions (3.3.2) on the citation parser's failures:
  an unparseable citation gets a specific message, and the en-dash trap (gotcha 17) must never
  surface as a bare 404 — if `s45a-1` was typed with a hyphen, say so and link the en-dash form.
- Autocomplete/combobox behaviour, if the box has any, follows the ARIA APG combobox pattern
  exactly; if it does not have any, do not add one in this task.

---

## A9 — Manual audit protocol (the part axe cannot answer)

Write `docs/a11y/manual-protocol.md` and run it once per phase, recording results in
`docs/a11y/manual-YYYY-MM-DD.md`. See `a11y-test-plan.md` in this package for the full protocol and
the sign-off sheet — copy it in rather than re-deriving it.

Minimum: keyboard-only completion of the five core tasks; NVDA/Firefox and VoiceOver/Safari passes
on a section page, a search result page and a redline; 200% zoom and 400% reflow at 320px; screen
magnifier at 400%; and one dictation/voice-control pass to confirm visible labels match accessible
names (2.5.3).

---

## A10 — Publish a conformance statement

Add `/app/accessibility`: the standard claimed (WCAG 2.1 AA), the date and method of the last
audit, the route matrix covered, **known exceptions with dates** — this project's ADR-0034 habit of
saying so where the controls would be applies here — and a contact route for reporting a barrier.
Link it from the global footer. Cover it in the guide, and let the guide ratchet keep it honest.
